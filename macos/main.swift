import Cocoa
import SwiftUI
import Combine

// MARK: - 数据模型
struct AgentUsage: Codable, Identifiable, Equatable {
    var id: String
    var name: String
    var totalTokens: Int
    var displayTokens: String
    var hitRate: Double
    var costCny: Double
    var sessionCount: Int
}

struct TodaySummary: Codable, Equatable {
    var date: String
    var totalTokens: Int
    var displayTokens: String
    var inputTokens: Int
    var cacheTokens: Int
    var outputTokens: Int
    var cacheHitRate: Double
    var latestSessionHitRate: Double?
    var latestSessionAgent: String?
    var costCny: Double
    var costUsd: Double
    var activeAgentsCount: Int
    var agents: [AgentUsage]

    static let placeholder = TodaySummary(
        date: "--",
        totalTokens: 0,
        displayTokens: "0",
        inputTokens: 0,
        cacheTokens: 0,
        outputTokens: 0,
        cacheHitRate: 0.0,
        latestSessionHitRate: nil,
        latestSessionAgent: nil,
        costCny: 0.0,
        costUsd: 0.0,
        activeAgentsCount: 0,
        agents: []
    )
}

// MARK: - 通用短格式 Token 格式化（两位数只显示小数点后1位，3位数及以上不显示小数点后数字）
func formatTokensShort(_ n: Int, fallback: String = "") -> String {
    guard n > 0 else { return fallback.isEmpty ? "0" : fallback }
    let val: Double
    let unit: String
    if n >= 1_000_000_000 {
        val = Double(n) / 1_000_000_000.0
        unit = "B"
    } else if n >= 1_000_000 {
        val = Double(n) / 1_000_000.0
        unit = "M"
    } else if n >= 1_000 {
        val = Double(n) / 1_000.0
        unit = "K"
    } else {
        return "\(n)"
    }
    
    if val >= 99.95 {
        return "\(Int(round(val)))\(unit)"
    } else if val >= 9.95 {
        return String(format: "%.1f%@", val, unit)
    } else {
        return unit == "K" ? String(format: "%.1fK", val) : String(format: "%.2f%@", val, unit)
    }
}

// MARK: - 状态管理
@MainActor
class AppState: ObservableObject {
    static let shared = AppState()
    
    @Published var summary: TodaySummary = .placeholder
    @Published var isLoading: Bool = false
    @Published var lastUpdated: Date? = nil
    @Published var isServerRunning: Bool = false
    @Published var arrowX: CGFloat = 155.0
    
    private var timer: Timer?
    private var pythonProcess: Process?
    let serverPort: Int = 8488
    
    private init() {}
    
    func start() {
        checkOrStartPythonServer()
        refreshData()
        
        // 启动 60 秒轮询定时器
        timer = Timer.scheduledTimer(withTimeInterval: 60.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.refreshData()
            }
        }
    }
    
    func refreshData(force: Bool = false) {
        guard !isLoading else { return }
        isLoading = true
        
        let urlStr = "http://127.0.0.1:\(serverPort)/api/today\(force ? "?refresh=1" : "")"
        guard let url = URL(string: urlStr) else {
            isLoading = false
            return
        }
        
        Task {
            var request = URLRequest(url: url)
            request.timeoutInterval = 5.0
            
            do {
                let (data, response) = try await URLSession.shared.data(for: request)
                if let httpResp = response as? HTTPURLResponse, httpResp.statusCode == 200 {
                    let decoded = try JSONDecoder().decode(TodaySummary.self, from: data)
                    await MainActor.run {
                        self.summary = decoded
                        self.lastUpdated = Date()
                        self.isServerRunning = true
                        self.isLoading = false
                        self.updateDockTile()
                    }
                } else {
                    await MainActor.run {
                        self.isLoading = false
                    }
                }
            } catch {
                await MainActor.run {
                    self.isLoading = false
                    // 若连接失败且后台尚未启动，尝试重新拉起服务
                    if !self.isServerRunning {
                        self.checkOrStartPythonServer()
                    }
                }
            }
        }
    }
    
    func updateDockTile() {
        let view = DockTileView(summary: self.summary)
        let hostingView = NSHostingView(rootView: view)
        hostingView.frame = NSRect(x: 0, y: 0, width: 128, height: 128)
        NSApp.dockTile.contentView = hostingView
        NSApp.dockTile.display()
    }
    
    func openWebDashboard() {
        if let url = URL(string: "http://127.0.0.1:\(serverPort)") {
            NSWorkspace.shared.open(url)
        }
    }
    
    private func checkOrStartPythonServer() {
        // 先简单测试端口连通性
        let testUrl = URL(string: "http://127.0.0.1:\(serverPort)/api/ping")!
        var req = URLRequest(url: testUrl)
        req.timeoutInterval = 1.0
        
        Task {
            do {
                let (_, resp) = try await URLSession.shared.data(for: req)
                if let http = resp as? HTTPURLResponse, http.statusCode == 200 {
                    await MainActor.run { self.isServerRunning = true }
                    return
                }
            } catch {
                // 服务未运行，启动 Python 子进程
                await MainActor.run { self.spawnPythonServer() }
            }
        }
    }
    
    private func spawnPythonServer() {
        guard pythonProcess == nil else { return }
        
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/bin/sh")
        
        // 探测工作目录与 PYTHONPATH：优先支持当前项目根目录与打包外层目录
        let appBundlePath = Bundle.main.bundlePath
        let distDir = (appBundlePath as NSString).deletingLastPathComponent
        let parentDir = (distDir as NSString).deletingLastPathComponent
        
        let cmd = """
        export PATH="/opt/anaconda3/bin:/usr/local/bin:/opt/homebrew/bin:$HOME/.local/bin:$PATH"
        export PYTHONPATH="\(parentDir):\(distDir):$PYTHONPATH"
        if command -v python3 >/dev/null 2>&1; then
            exec python3 -m myccusage_lib.cli --web --daemon --port \(serverPort) --no-open
        elif command -v myccusage >/dev/null 2>&1; then
            exec myccusage --web --daemon --port \(serverPort) --no-open
        fi
        """
        proc.arguments = ["-c", cmd]
        
        let logPath = "/tmp/myccusage_daemon.log"
        FileManager.default.createFile(atPath: logPath, contents: nil)
        if let logHandle = FileHandle(forWritingAtPath: logPath) {
            proc.standardOutput = logHandle
            proc.standardError = logHandle
        }
        
        do {
            try proc.run()
            self.pythonProcess = proc
            self.isServerRunning = true
            
            // 稍等 1 秒后抓取初始数据
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                self.refreshData()
            }
        } catch {
            print("启动后台服务失败: \(error)")
        }
    }
    
    func terminate() {
        timer?.invalidate()
        if let proc = pythonProcess, proc.isRunning {
            proc.terminate()
        }
    }
}

// MARK: - 颜色与图标辅助
struct AgentTheme {
    static func color(for id: String) -> Color {
        switch id {
        case "agy": return Color(red: 0.26, green: 0.52, blue: 0.96)     // Google Blue
        case "claude": return Color(red: 0.85, green: 0.45, blue: 0.32)  // Anthropic Terracotta
        case "codex": return Color(red: 0.12, green: 0.72, blue: 0.53)   // OpenAI Emerald
        case "hermes": return Color(red: 0.98, green: 0.55, blue: 0.15)  // Hermes Orange
        case "workbuddy": return Color(red: 0.40, green: 0.45, blue: 0.95)// WorkBuddy Indigo
        case "grok": return Color(red: 0.95, green: 0.25, blue: 0.35)    // Grok Crimson
        case "opencode": return Color(red: 0.20, green: 0.75, blue: 0.85) // Cyan
        default: return Color.gray
        }
    }
    
    static func icon(for id: String) -> String {
        switch id {
        case "agy": return "sparkles"
        case "claude": return "brain.head.profile"
        case "codex": return "terminal.fill"
        case "hermes": return "bolt.horizontal.fill"
        case "workbuddy": return "briefcase.fill"
        case "grok": return "flame.fill"
        case "opencode": return "chevron.left.forwardslash.chevron.right"
        default: return "circle.fill"
        }
    }
}

// MARK: - Dock Tile 微型动态看板视图 (128x128)
struct DockTileView: View {
    let summary: TodaySummary
    
    // 外圈环形：读取最新一次刷新得到的最近一个 session 命中率（从 30% 起跳）
    var cacheProgress: Double {
        let rate = summary.latestSessionHitRate ?? summary.cacheHitRate
        if rate <= 30.0 {
            return 0.0
        }
        return min(max((rate - 30.0) / 70.0, 0.0), 1.0)
    }
    
    // 每日一亿 Token (100M) 进度比例
    var goalProgress: Double {
        return min(max(Double(summary.totalTokens) / 100_000_000.0, 0.0), 1.0)
    }
    
    var body: some View {
        ZStack {
            // 背景底座：深色圆角方块
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Color(red: 0.10, green: 0.11, blue: 0.14),
                            Color(red: 0.05, green: 0.06, blue: 0.08)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 26, style: .continuous)
                        .stroke(Color.white.opacity(0.12), lineWidth: 1)
                )
            
            // 外圈环形进度条：最近活跃 Session 的 KV Cache 命中率 (从 30% 起跳，青蓝至薄荷绿渐变)
            Circle()
                .stroke(Color.white.opacity(0.08), lineWidth: 6.5)
                .padding(14)
            
            Circle()
                .trim(from: 0, to: CGFloat(cacheProgress))
                .stroke(
                    AngularGradient(
                        gradient: Gradient(colors: [
                            Color(red: 0.15, green: 0.75, blue: 0.95), // Cyan
                            Color(red: 0.20, green: 0.92, blue: 0.65), // Mint
                            Color(red: 0.15, green: 0.75, blue: 0.95)
                        ]),
                        center: .center,
                        startAngle: .degrees(-90),
                        endAngle: .degrees(270)
                    ),
                    style: StrokeStyle(lineWidth: 6.5, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .padding(14)
                .shadow(color: Color(red: 0.20, green: 0.92, blue: 0.65).opacity(0.4), radius: 4)
            
            // 核心数值与信息层
            VStack(spacing: 7) {
                // 顶部：纯粹无文字、饱满厚实的每日 100M 目标进度条
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(Color.white.opacity(0.15))
                        Capsule()
                            .fill(
                                LinearGradient(
                                    colors: [
                                        Color(red: 1.0, green: 0.72, blue: 0.15),
                                        Color(red: 1.0, green: 0.50, blue: 0.10)
                                    ],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                            .frame(width: max(4, geo.size.width * CGFloat(goalProgress)))
                            .shadow(color: Color(red: 1.0, green: 0.60, blue: 0.12).opacity(0.45), radius: 3)
                    }
                }
                .frame(width: 66, height: 5.5) // 宽度 66pt，高度 5.5pt，丰满纯粹
                .padding(.top, 6)
                
                // 今日 Token 总量大字展示（两位数只显示小数点后1位，3位数及以上不显示小数点后数字）
                Text(dockDisplayTokens)
                    .font(.system(size: dockDisplayTokens.count > 5 ? 24 : (dockDisplayTokens.count > 4 ? 27 : 30), weight: .heavy, design: .rounded))
                    .foregroundColor(.white)
                    .minimumScaleFactor(0.7)
                    .lineLimit(1)
                    .padding(.bottom, 2)
            }
            .padding(10)
        }
        .frame(width: 128, height: 128)
    }
    
    private var dockDisplayTokens: String {
        if summary.totalTokens > 0 {
            return formatTokensShort(summary.totalTokens, fallback: summary.displayTokens)
        }
        return summary.displayTokens
    }
}

// MARK: - 悬浮卡片全局配置常量
private let popoverCardWidth: CGFloat = 340

// MARK: - 悬浮卡片视图 (参考用户 Status Trio 风格设计)
struct FloatingPopoverView: View {
    @ObservedObject var state = AppState.shared
    var onOpenWeb: () -> Void
    var onRefresh: () -> Void
    var onQuit: () -> Void
    
    var body: some View {
        VStack(spacing: 0) {
            // 1. 顶部 Header：今日全景卡片
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    HStack(spacing: 6) {
                        Image(systemName: "bolt.circle.fill")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(Color(red: 0.20, green: 0.85, blue: 0.60))
                        Text("今日 AI Token 用量")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(.primary)
                            .lineLimit(1)
                    }
                    
                    Spacer()
                    
                    if state.isLoading {
                        ProgressView()
                            .scaleEffect(0.6)
                            .frame(width: 14, height: 14)
                    } else if let last = state.lastUpdated {
                        Text(formatTime(last))
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                }
                
                // 主大字与数据指标行 (支持三位数 + M/K 宽裕排版，严防多行折字)
                HStack(alignment: .lastTextBaseline, spacing: 0) {
                    // 左侧：主 Token 数值展示
                    HStack(alignment: .lastTextBaseline, spacing: 4) {
                        Text(state.summary.displayTokens)
                            .font(.system(
                                size: state.summary.displayTokens.count >= 6 ? 26 : (state.summary.displayTokens.count == 5 ? 28 : 32),
                                weight: .black,
                                design: .rounded
                            ))
                            .foregroundColor(.primary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                        
                        Text("Tokens")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                    .fixedSize(horizontal: true, vertical: false)
                    
                    Spacer(minLength: 14)
                    
                    // 右侧：命中率与费用指标 (独立尺寸锁定，保证单行工整)
                    HStack(spacing: 8) {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text("缓存命中")
                                .font(.system(size: 10))
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                            Text("\(String(format: "%.1f", state.summary.cacheHitRate))%")
                                .font(.system(size: 13, weight: .heavy, design: .rounded))
                                .foregroundColor(Color(red: 0.15, green: 0.75, blue: 0.95))
                                .lineLimit(1)
                        }
                        
                        Divider().frame(height: 22).padding(.horizontal, 2)
                        
                        VStack(alignment: .trailing, spacing: 2) {
                            Text("估算费用")
                                .font(.system(size: 10))
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                            Text("¥\(String(format: "%.2f", state.summary.costCny))")
                                .font(.system(size: 13, weight: .heavy, design: .rounded))
                                .foregroundColor(.primary)
                                .lineLimit(1)
                        }
                    }
                    .fixedSize(horizontal: true, vertical: false)
                }
            }
            .padding(14)
            
            Divider().opacity(0.4)
            
            // 2. 中部：活跃 Agent 明细列表 (参考图清单结构)
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("Agent 明细")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.secondary)
                        .textCase(.uppercase)
                    Spacer()
                    Text("用量 · 缓存率")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .padding(.horizontal, 14)
                .padding(.top, 10)
                .padding(.bottom, 6)
                
                if state.summary.agents.isEmpty {
                    HStack {
                        Spacer()
                        Text("今日暂无 Agent 交互记录")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                            .padding(.vertical, 16)
                        Spacer()
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 2) {
                            ForEach(state.summary.agents) { agent in
                                AgentRowView(agent: agent)
                            }
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                    }
                    .frame(maxHeight: 180)
                }
            }
            
            Divider().opacity(0.4)
            
            // 3. 底部操作栏（打开完整看板、刷新、退出）
            VStack(spacing: 2) {
                // 重点推荐入口：打开原有的完整精美 Web 看板
                Button(action: onOpenWeb) {
                    HStack(spacing: 8) {
                        Image(systemName: "safari.fill")
                            .font(.system(size: 13))
                            .foregroundColor(.blue)
                        Text("打开完整看板 (Web 账本)")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.primary)
                        Spacer()
                        Image(systemName: "arrow.up.right")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.secondary)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .contentShape(Rectangle())
                }
                .buttonStyle(PlainHoverButtonStyle())
                
                // 立即刷新
                Button(action: onRefresh) {
                    HStack(spacing: 8) {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                        Text("立即刷新数据")
                            .font(.system(size: 12))
                            .foregroundColor(.primary)
                        Spacer()
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .contentShape(Rectangle())
                }
                .buttonStyle(PlainHoverButtonStyle())
                
                // 退出应用
                Button(action: onQuit) {
                    HStack(spacing: 8) {
                        Image(systemName: "power")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                        Text("退出 myccusage")
                            .font(.system(size: 12))
                            .foregroundColor(.primary)
                        Spacer()
                        Text("⌘Q")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .contentShape(Rectangle())
                }
                .buttonStyle(PlainHoverButtonStyle())
            }
            .padding(6)
        }
        .frame(width: popoverCardWidth)
        .background(
            // 原生磨砂玻璃背景
            VisualEffectBlur(material: .popover, blendingMode: .behindWindow)
        )
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.white.opacity(0.24), lineWidth: 0.8)
        )
    }
    
    private func formatTime(_ date: Date) -> String {
        let df = DateFormatter()
        df.dateFormat = "HH:mm:ss"
        return df.string(from: date)
    }
}

// 带对话气泡指向尖角的完整弹出容器
struct AnchoredPopoverContainerView: View {
    @ObservedObject var state = AppState.shared
    var onOpenWeb: () -> Void
    var onRefresh: () -> Void
    var onQuit: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // 主卡片主体
            FloatingPopoverView(
                state: state,
                onOpenWeb: onOpenWeb,
                onRefresh: onRefresh,
                onQuit: onQuit
            )
            
            // 底部对话气泡呼应小尖尖 (Arrow Tip，直指底部的 Dock 图标)
            GeometryReader { geo in
                let clampedX = max(24, min(state.arrowX, geo.size.width - 24))
                Path { path in
                    path.move(to: CGPoint(x: clampedX - 10, y: 0))
                    path.addLine(to: CGPoint(x: clampedX, y: 9))
                    path.addLine(to: CGPoint(x: clampedX + 10, y: 0))
                    path.closeSubpath()
                }
                .fill(Color(nsColor: .windowBackgroundColor).opacity(0.96))
                .overlay(
                    Path { path in
                        path.move(to: CGPoint(x: clampedX - 10, y: 0))
                        path.addLine(to: CGPoint(x: clampedX, y: 9))
                        path.addLine(to: CGPoint(x: clampedX + 10, y: 0))
                    }
                    .stroke(Color.white.opacity(0.24), lineWidth: 0.8)
                )
            }
            .frame(height: 9)
            .offset(y: -0.5) // 与卡片底边无缝贴合
        }
        .frame(width: popoverCardWidth)
        .shadow(color: Color.black.opacity(0.25), radius: 12, x: 0, y: 6)
        .padding(.bottom, 2)
    }
}

// MARK: - 单个 Agent 列表行
struct AgentRowView: View {
    let agent: AgentUsage
    
    var body: some View {
        HStack(spacing: 8) {
            // 图标徽标
            ZStack {
                Circle()
                    .fill(AgentTheme.color(for: agent.id).opacity(0.18))
                    .frame(width: 26, height: 26)
                Image(systemName: AgentTheme.icon(for: agent.id))
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(AgentTheme.color(for: agent.id))
            }
            
            // 名称与会话数
            VStack(alignment: .leading, spacing: 2) {
                Text(agent.name)
                    .font(.system(size: 12, weight: .semibold))
                    .lineLimit(1)
                
                // 微型进度条展示命中率
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(Color.primary.opacity(0.08))
                            .frame(height: 3)
                        Capsule()
                            .fill(AgentTheme.color(for: agent.id))
                            .frame(width: max(0, min(geo.size.width * CGFloat(agent.hitRate / 100.0), geo.size.width)), height: 3)
                    }
                }
                .frame(height: 3)
            }
            
            Spacer()
            
            // Token 数值与命中率
            VStack(alignment: .trailing, spacing: 1) {
                Text(agent.displayTokens)
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundColor(.primary)
                    .lineLimit(1)
                Text("\(String(format: "%.0f", agent.hitRate))% 命中")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }
            .fixedSize(horizontal: true, vertical: false)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 5)
        .background(Color.primary.opacity(0.02))
        .cornerRadius(8)
    }
}

// 悬停样式支持
struct PlainHoverButtonStyle: ButtonStyle {
    @State private var isHovered = false
    
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isHovered ? Color.primary.opacity(0.08) : Color.clear)
            )
            .onHover { isHovered = $0 }
    }
}

// 原生毛玻璃背景桥接
struct VisualEffectBlur: NSViewRepresentable {
    var material: NSVisualEffectView.Material
    var blendingMode: NSVisualEffectView.BlendingMode

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = material
        nsView.blendingMode = blendingMode
    }
}

// MARK: - 原生悬浮 Panel 窗口
class FloatingPopoverWindow: NSPanel {
    init(contentView: NSView) {
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: popoverCardWidth, height: 300),
            styleMask: [.nonactivatingPanel, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = false // 由 SwiftUI 统一提供高保真阴影
        self.level = .floating
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.contentView = contentView
        self.isMovableByWindowBackground = false
    }
    
    override var canBecomeKey: Bool {
        return true
    }
    
    func showNearDock() {
        guard let screen = NSScreen.main else {
            self.center()
            self.makeKeyAndOrderFront(nil)
            return
        }
        
        // 核心修复：根据 SwiftUI 实际撑开的内容高度动态收紧窗口，杜绝窗口空高导致的贴紧 Dock
        if let hv = self.contentView {
            let fit = hv.fittingSize
            if fit.width > 0 && fit.height > 0 {
                self.setContentSize(NSSize(width: popoverCardWidth, height: fit.height))
            }
        }
        
        let screenRect = screen.visibleFrame
        let fullRect = screen.frame
        let windowSize = self.frame.size
        let mouseLoc = NSEvent.mouseLocation
        
        var targetX: CGFloat
        var targetY: CGFloat
        var initialY: CGFloat
        
        // 1. 判断 Dock 方向
        let isLeftDock = screenRect.minX > fullRect.minX
        let isRightDock = screenRect.maxX < fullRect.maxX
        
        if isLeftDock {
            targetX = screenRect.minX + 16
            let anchorY = (mouseLoc.y > 0 && mouseLoc.x < screenRect.minX + 60) ? mouseLoc.y : screenRect.midY
            targetY = anchorY - (windowSize.height / 2)
            initialY = targetY
        } else if isRightDock {
            targetX = screenRect.maxX - windowSize.width - 16
            let anchorY = (mouseLoc.y > 0 && mouseLoc.x > screenRect.maxX - 60) ? mouseLoc.y : screenRect.midY
            targetY = anchorY - (windowSize.height / 2)
            initialY = targetY
        } else {
            // 绝大多数：Dock 在屏幕底部
            let isMouseInDock = (mouseLoc.y <= screenRect.minY + 60 && mouseLoc.x >= screenRect.minX && mouseLoc.x <= screenRect.maxX)
            let anchorX = isMouseInDock ? mouseLoc.x : screenRect.midX
            
            targetX = anchorX - (windowSize.width / 2)
            // 核心修复：与 Dock 顶边缘拉开足够距离（尖尖尖端距离 Dock 10pt，卡片底边距离 Dock 19pt）
            targetY = screenRect.minY + 12
            initialY = targetY - 14 // 从下方延伸升起
        }
        
        targetX = max(screenRect.minX + 12, min(targetX, screenRect.maxX - windowSize.width - 12))
        targetY = max(screenRect.minY + 12, min(targetY, screenRect.maxY - windowSize.height - 12))
        
        // 动态计算气泡小尖尖相对于窗口的水平中心，确保 100% 精准指向图标
        let relativeArrowX = (mouseLoc.x > 0) ? (mouseLoc.x - targetX) : (windowSize.width / 2)
        AppState.shared.arrowX = relativeArrowX
        
        // 初始动画状态
        self.setFrameOrigin(NSPoint(x: targetX, y: initialY))
        self.alphaValue = 0.0
        self.makeKeyAndOrderFront(nil)
        
        // 向上延伸升起动效
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.18
            ctx.timingFunction = CAMediaTimingFunction(name: .easeOut)
            self.animator().setFrameOrigin(NSPoint(x: targetX, y: targetY))
            self.animator().alphaValue = 1.0
        }
    }
    
    func hideAnimated() {
        let currentOrigin = self.frame.origin
        let shrinkY = currentOrigin.y - 12 // 向下缩回图标
        
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.12
            ctx.timingFunction = CAMediaTimingFunction(name: .easeIn)
            self.animator().setFrameOrigin(NSPoint(x: currentOrigin.x, y: shrinkY))
            self.animator().alphaValue = 0.0
        }, completionHandler: {
            self.orderOut(nil)
        })
    }
}

// MARK: - AppKit 委托与生命周期
class AppDelegate: NSObject, NSApplicationDelegate {
    private var popoverWindow: FloatingPopoverWindow?
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        // 设置应用在 Dock 栏常驻显示
        NSApp.setActivationPolicy(.regular)
        
        // 创建带呼应小尖尖的一体化气泡卡片
        let popoverContent = AnchoredPopoverContainerView(
            onOpenWeb: { [weak self] in
                AppState.shared.openWebDashboard()
                self?.popoverWindow?.hideAnimated()
            },
            onRefresh: {
                AppState.shared.refreshData(force: true)
            },
            onQuit: {
                NSApp.terminate(nil)
            }
        )
        
        let hostingView = NSHostingView(rootView: popoverContent)
        self.popoverWindow = FloatingPopoverWindow(contentView: hostingView)
        
        // 监听失焦事件，点击桌面其他区域自动平滑收起
        NotificationCenter.default.addObserver(
            forName: NSWindow.didResignKeyNotification,
            object: self.popoverWindow,
            queue: .main
        ) { [weak self] _ in
            self?.popoverWindow?.hideAnimated()
        }
        
        // 启动后台服务与轮询
        AppState.shared.start()
        
        // 初始化 Dock Tile 渲染
        AppState.shared.updateDockTile()
    }
    
    // 点击 Dock 图标时触发展开 / 收起
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        guard let window = self.popoverWindow else { return true }
        
        if window.isVisible && window.alphaValue > 0.5 {
            window.hideAnimated()
        } else {
            window.showNearDock()
        }
        return false
    }
    
    func applicationWillTerminate(_ notification: Notification) {
        AppState.shared.terminate()
    }
}

// MARK: - 纯代码启动器
@main
struct Launcher {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.run()
    }
}

