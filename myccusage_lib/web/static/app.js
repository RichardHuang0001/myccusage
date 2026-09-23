/**
 * myccusage Web Dashboard 前端交互逻辑
 * 纯原生 JavaScript 实现，零框架重型依赖，极速响应。
 */

(function () {
  'use strict';

  // 格式化单价（避免 0.025 等高精度小数被无故截断或四舍五入）
  function formatRate(rate) {
    if (typeof rate !== 'number') rate = parseFloat(rate) || 0;
    if (rate % 1 === 0) return rate.toFixed(1);
    return Number(rate.toFixed(4)).toString();
  }

  // 系统预设计价模型库（已通过官方最新文档校验）
  const DEFAULT_PRICING_MODELS = {
    'deepseek-v4.1-flash': {
      id: 'deepseek-v4.1-flash',
      name: 'DeepSeek-V4.1-Flash (高峰期)',
      badge: '官方高峰期',
      currency: 'CNY',
      inputRate: 2.0,
      cacheRate: 0.04,
      outputRate: 8.0,
      isBuiltin: true,
      note: '官方高峰期计费标准 (输入未命中 ¥2/M | 缓存命中 ¥0.04/M | 输出 ¥8/M)'
    },
    'deepseek-v4.1-flash-offpeak': {
      id: 'deepseek-v4.1-flash-offpeak',
      name: 'DeepSeek-V4.1-Flash (低谷期)',
      badge: '官方低谷期',
      currency: 'CNY',
      inputRate: 1.0,
      cacheRate: 0.02,
      outputRate: 4.0,
      isBuiltin: true,
      note: '官方空闲低谷期计费标准 (输入未命中 ¥1/M | 缓存命中 ¥0.02/M | 输出 ¥4/M)'
    },
    'glm-5.3-flash': {
      id: 'glm-5.3-flash',
      name: 'GLM-5.3-Flash (正式刊例价)',
      badge: '智谱AI标准价',
      currency: 'CNY',
      inputRate: 0.8,
      cacheRate: 0.23,
      outputRate: 2.8,
      isBuiltin: true,
      note: '智谱AI官方正式刊例价 (输入未命中 ¥0.8/M | 缓存命中 ¥0.23/M | 输出 ¥2.8/M)'
    },
    'gpt-6-astra': {
      id: 'gpt-6-astra',
      name: 'GPT-6 Astra',
      badge: 'OpenAI超旗舰',
      currency: 'USD',
      inputRate: 10.0,
      cacheRate: 1.0,
      outputRate: 50.0,
      isBuiltin: true,
      note: 'OpenAI官方超旗舰标准 (输入未命中 $10/M | 缓存命中 $1/M | 输出 $50/M)'
    },
    'gpt-5.6-sol': {
      id: 'gpt-5.6-sol',
      name: 'GPT-5.6 Sol',
      badge: 'OpenAI主力旗舰',
      currency: 'USD',
      inputRate: 4.0,
      cacheRate: 0.4,
      outputRate: 20.0,
      isBuiltin: true,
      note: 'OpenAI智能体主力旗舰 (输入未命中 $4/M | 缓存命中 $0.4/M | 输出 $20/M)'
    },
    'gpt-5.6-terra': {
      id: 'gpt-5.6-terra',
      name: 'GPT-5.6 Terra',
      badge: 'OpenAI均衡主力',
      currency: 'USD',
      inputRate: 2.0,
      cacheRate: 0.2,
      outputRate: 12.0,
      isBuiltin: true,
      note: 'OpenAI高吞吐均衡主力 (输入未命中 $2/M | 缓存命中 $0.2/M | 输出 $12/M)'
    },
    'claude-opus-5': {
      id: 'claude-opus-5',
      name: 'Claude Opus 5',
      badge: 'Anthropic旗舰',
      currency: 'USD',
      inputRate: 5.0,
      cacheRate: 0.5,
      outputRate: 25.0,
      isBuiltin: true,
      note: 'Anthropic前沿推理旗舰 (输入未命中 $5/M | 缓存命中 $0.5/M | 输出 $25/M)'
    },
    'claude-sonnet-5': {
      id: 'claude-sonnet-5',
      name: 'Claude Sonnet 5',
      badge: 'Anthropic主力',
      currency: 'USD',
      inputRate: 2.0,
      cacheRate: 0.2,
      outputRate: 10.0,
      isBuiltin: true,
      note: 'Anthropic通用综合标杆主力 (输入未命中 $2/M | 缓存命中 $0.2/M | 输出 $10/M)'
    },
    'claude-haiku-4.5': {
      id: 'claude-haiku-4.5',
      name: 'Claude Haiku 4.5',
      badge: 'Anthropic轻量',
      currency: 'USD',
      inputRate: 1.0,
      cacheRate: 0.1,
      outputRate: 5.0,
      isBuiltin: true,
      note: 'Anthropic极速高吞吐主力 (输入未命中 $1/M | 缓存命中 $0.1/M | 输出 $5/M)'
    },
    'grok-4.6': {
      id: 'grok-4.6',
      name: 'Grok 4.6',
      badge: 'xAI最新旗舰',
      currency: 'USD',
      inputRate: 2.0,
      cacheRate: 0.5,
      outputRate: 6.0,
      isBuiltin: true,
      note: 'xAI最新旗舰模型 (输入未命中 $2/M | 缓存命中 $0.5/M | 输出 $6/M)'
    },
    'mimo-v2.5-pro': {
      id: 'mimo-v2.5-pro',
      name: 'MiMo-V2.5-Pro',
      badge: '小米官方',
      currency: 'CNY',
      inputRate: 3.0,
      cacheRate: 0.025,
      outputRate: 6.0,
      isBuiltin: true,
      note: '小米官方按量计费标准 (输入未命中 ¥3/M | 缓存命中 ¥0.025/M | 输出 ¥6/M)'
    }
  };

  // 本地轻量持久化存储 (高内聚、零冗余中间文件)
  function getCustomModels() {
    try {
      const raw = localStorage.getItem('myccusage_custom_pricing_models');
      return raw ? JSON.parse(raw) : {};
    } catch (e) {
      return {};
    }
  }

  function saveCustomModels(models) {
    try {
      localStorage.setItem('myccusage_custom_pricing_models', JSON.stringify(models));
    } catch (e) {}
  }

  function getDeletedModelIds() {
    try {
      const raw = localStorage.getItem('myccusage_deleted_model_ids');
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  function saveDeletedModelIds(ids) {
    try {
      localStorage.setItem('myccusage_deleted_model_ids', JSON.stringify(ids));
    } catch (e) {}
  }

  function getAllPricingModels() {
    const deleted = getDeletedModelIds();
    const all = Object.assign({}, DEFAULT_PRICING_MODELS, getCustomModels());
    deleted.forEach(id => {
      delete all[id];
    });
    return all;
  }

  function getActiveModel() {
    const all = getAllPricingModels();
    if (all[state.pricingModel]) return all[state.pricingModel];
    const firstKey = Object.keys(all)[0];
    return firstKey ? all[firstKey] : DEFAULT_PRICING_MODELS['deepseek-v4.1-flash'];
  }

  // 从 URL 参数中读取默认 Agent（若未指定则默认全新主打 “all” 全景对比）
  const initialUrlParams = new URLSearchParams(window.location.search);
  const initialAgent = initialUrlParams.get('agent') || 'all';

  // 全局状态
  const state = {
    agent: initialAgent,
    mode: 'daily',
    sort: 'time',
    timeSortOrder: 'desc', // Web 端默认时间倒序 (最新在最顶上)
    pricingModel: 'deepseek-v4.1-flash',
    managingModelId: 'deepseek-v4.1-flash',
    searchQuery: '',
    data: null,
    allAgentsData: null,
    trendChartInstance: null,
    donutChartInstance: null,
    isDarkTheme: true,
    raceRange: '30',
    highlightedAgent: null,
    hiddenAgents: new Set(),
    raceChartInstance: null,
    syncState: null
  };

  // DOM 元素缓存
  const el = {
    agentSelector: document.getElementById('agentSelector'),
    modeSelector: document.getElementById('modeSelector'),
    btnSortTime: document.getElementById('btnSortTime'),
    btnSortTokens: document.getElementById('btnSortTokens'),
    btnSync: document.getElementById('btnSync'),
    btnSyncSettings: document.getElementById('btnSyncSettings'),
    syncIcon: document.getElementById('syncIcon'),
    syncBtnText: document.getElementById('syncBtnText'),
    btnRefresh: document.getElementById('btnRefresh'),
    btnThemeToggle: document.getElementById('btnThemeToggle'),
    themeIcon: document.getElementById('themeIcon'),
    liveStatus: document.getElementById('liveStatus'),
    searchInput: document.getElementById('searchInput'),
    btnClearSearch: document.getElementById('btnClearSearch'),
    btnToggleAllAccordion: document.getElementById('btnToggleAllAccordion'),
    recordCounter: document.getElementById('recordCounter'),

    // 多端 Git 同步弹窗
    syncModal: document.getElementById('syncModal'),
    btnCloseSyncModal: document.getElementById('btnCloseSyncModal'),
    syncSetupView: document.getElementById('syncSetupView'),
    syncManageView: document.getElementById('syncManageView'),
    syncRepoUrl: document.getElementById('syncRepoUrl'),
    syncDeviceName: document.getElementById('syncDeviceName'),
    syncDeviceId: document.getElementById('syncDeviceId'),
    btnConfirmSyncSetup: document.getElementById('btnConfirmSyncSetup'),
    btnCancelSyncSetup: document.getElementById('btnCancelSyncSetup'),
    syncStatusBadge: document.getElementById('syncStatusBadge'),
    syncLastTime: document.getElementById('syncLastTime'),
    syncCurrentDeviceDisplay: document.getElementById('syncCurrentDeviceDisplay'),
    syncRepoUrlDisplay: document.getElementById('syncRepoUrlDisplay'),
    syncDeviceCount: document.getElementById('syncDeviceCount'),
    syncDeviceList: document.getElementById('syncDeviceList'),
    btnUnbindSync: document.getElementById('btnUnbindSync'),
    btnCloseSyncView: document.getElementById('btnCloseSyncView'),
    btnTriggerModalSync: document.getElementById('btnTriggerModalSync'),

    // 多端同步进度实时气泡
    syncPopover: document.getElementById('syncPopover'),
    btnCloseSyncPopover: document.getElementById('btnCloseSyncPopover'),
    syncPopoverTitle: document.getElementById('syncPopoverTitle'),
    syncPopoverDot: document.getElementById('syncPopoverDot'),
    syncPopoverError: document.getElementById('syncPopoverError'),
    syncPopoverErrorMsg: document.getElementById('syncPopoverErrorMsg'),

    // 计价下拉
    pricingDropdownContainer: document.getElementById('pricingDropdownContainer'),
    pricingTrigger: document.getElementById('pricingTrigger'),
    selectedPricingName: document.getElementById('selectedPricingName'),
    pricingMenu: document.getElementById('pricingMenu'),
    pricingOptionsList: document.getElementById('pricingOptionsList'),
    pricingFloatingPopover: document.getElementById('pricingFloatingPopover'),
    btnOpenModelManager: document.getElementById('btnOpenModelManager'),

    // KPI 元素
    valTotalTokens: document.getElementById('valTotalTokens'),
    subTotalTokens: document.getElementById('subTotalTokens'),
    valTotalCost: document.getElementById('valTotalCost'),
    valTotalCostUsd: document.getElementById('valTotalCostUsd'),
    valCacheHitRate: document.getElementById('valCacheHitRate'),
    barCacheHit: document.getElementById('barCacheHit'),
    valActiveDays: document.getElementById('valActiveDays'),
    subActiveDays: document.getElementById('subActiveDays'),
    valRecordsCount: document.getElementById('valRecordsCount'),
    badgeActivePeriod: document.getElementById('badgeActivePeriod'),
    badgeRecordsType: document.getElementById('badgeRecordsType'),
    subRecordsDetail: document.getElementById('subRecordsDetail'),

    // 今日指标卡片 (新增)
    valTodayTokens: document.getElementById('valTodayTokens'),
    valTodayCost: document.getElementById('valTodayCost'),
    subTodayDetail: document.getElementById('subTodayDetail'),
    titleTodayUsage: document.getElementById('titleTodayUsage'),
    badgeToday: document.getElementById('badgeToday'),

    // 7天 / 14天 滚动指标卡片
    val7DaysTokens: document.getElementById('val7DaysTokens'),
    val7DaysCost: document.getElementById('val7DaysCost'),
    val7DaysAvgTokens: document.getElementById('val7DaysAvgTokens'),
    val7DaysAvgCost: document.getElementById('val7DaysAvgCost'),
    val14DaysTokens: document.getElementById('val14DaysTokens'),
    val14DaysCost: document.getElementById('val14DaysCost'),
    val14DaysAvgTokens: document.getElementById('val14DaysAvgTokens'),
    val14DaysAvgCost: document.getElementById('val14DaysAvgCost'),

    // 视图容器
    chartsSection: document.getElementById('chartsSection'),
    allAgentsSection: document.getElementById('allAgentsSection'),
    agentsOverviewGrid: document.getElementById('agentsOverviewGrid'),
    tableSection: document.getElementById('tableSection'),
    raceChartSection: document.getElementById('raceChartSection'),
    raceChartCanvas: document.getElementById('raceChartCanvas'),
    raceYAxisLeft: document.getElementById('raceYAxisLeft'),
    raceScrollViewport: document.getElementById('raceScrollViewport'),
    raceScrollCanvasWrap: document.getElementById('raceScrollCanvasWrap'),
    raceLegendBar: document.getElementById('raceLegendBar'),
    raceRangeSelector: document.getElementById('raceRangeSelector'),
    raceChartFallback: document.getElementById('raceChartFallback'),
    ledgerContainer: document.getElementById('ledgerContainer'),
    toast: document.getElementById('toast'),

    // Canvas 与内部横滑图表
    trendChartCanvas: document.getElementById('trendChartCanvas'),
    trendYAxisLeft: document.getElementById('trendYAxisLeft'),
    trendYAxisRight: document.getElementById('trendYAxisRight'),
    trendScrollViewport: document.getElementById('trendScrollViewport'),
    trendScrollCanvasWrap: document.getElementById('trendScrollCanvasWrap'),
    trendScrollBarWrap: document.getElementById('trendScrollBarWrap'),
    trendScrollHintText: document.getElementById('trendScrollHintText'),
    btnSnapLatest: document.getElementById('btnSnapLatest'),
    donutChartCanvas: document.getElementById('donutChartCanvas'),
    donutStats: document.getElementById('donutStats'),
    trendChartTitle: document.getElementById('trendChartTitle'),

    // 模型管理弹窗 (二级)
    modelManagerModal: document.getElementById('modelManagerModal'),
    btnCloseManagerModal: document.getElementById('btnCloseManagerModal'),
    modelCountBadge: document.getElementById('modelCountBadge'),
    manageModelList: document.getElementById('manageModelList'),
    btnOpenAddModelModal: document.getElementById('btnOpenAddModelModal'),
    btnResetDefaultModels: document.getElementById('btnResetDefaultModels'),
    manageModelDetail: document.getElementById('manageModelDetail'),
    detailModelTitle: document.getElementById('detailModelTitle'),
    detailModelBadge: document.getElementById('detailModelBadge'),
    btnApplySelectedModel: document.getElementById('btnApplySelectedModel'),
    editModelName: document.getElementById('editModelName'),
    editModelCurrency: document.getElementById('editModelCurrency'),
    symbolInputRate: document.getElementById('symbolInputRate'),
    editModelInput: document.getElementById('editModelInput'),
    symbolCacheRate: document.getElementById('symbolCacheRate'),
    editModelCache: document.getElementById('editModelCache'),
    symbolOutputRate: document.getElementById('symbolOutputRate'),
    editModelOutput: document.getElementById('editModelOutput'),
    editModelNote: document.getElementById('editModelNote'),
    btnSaveModelEdit: document.getElementById('btnSaveModelEdit'),
    btnDeleteModel: document.getElementById('btnDeleteModel'),

    // 智能导入弹窗 (三级)
    addModelModal: document.getElementById('addModelModal'),
    btnCloseAddModal: document.getElementById('btnCloseAddModal'),
    btnCancelAddModal: document.getElementById('btnCancelAddModal'),
    btnCopyAiPrompt: document.getElementById('btnCopyAiPrompt'),
    aiPromptCodeBox: document.getElementById('aiPromptCodeBox'),
    btnLoadExample: document.getElementById('btnLoadExample'),
    importConfigText: document.getElementById('importConfigText'),
    importPreviewContainer: document.getElementById('importPreviewContainer'),
    parseStatusBar: document.getElementById('parseStatusBar'),
    btnConfirmImportModel: document.getElementById('btnConfirmImportModel')
  };

  // 工具函数
  function formatTokens(n) {
    if (!n || n === 0) return '0';
    if (n >= 1000000000) return (n / 1000000000).toFixed(2) + 'B';
    if (n >= 1000000) return (n / 1000000).toFixed(2) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
  }

  function calcHitRateStr(cache, inp) {
    const denom = (cache || 0) + (inp || 0);
    if (denom <= 0) return '0.0%';
    return ((cache / denom) * 100).toFixed(1) + '%';
  }

  // 高性能纯内存计费重算引擎 (无任何临时文件与冗余开销)
  function calcCost(model, inpTokens, cacheTokens, outTokens) {
    const m = model || getActiveModel();
    const inp = ((inpTokens || 0) / 1000000) * (m.inputRate || 0);
    const cache = ((cacheTokens || 0) / 1000000) * (m.cacheRate || 0);
    const out = ((outTokens || 0) / 1000000) * (m.outputRate || 0);
    return inp + cache + out;
  }

  // 汇率换算基准 (固定汇率基准 1 USD = 7.2 CNY)
  const USD_CNY_RATE = 7.2;

  // 将任意模型计算出的金额统一换算为人民币 (CNY ¥)
  function toCnyCost(model, costVal) {
    const m = model || getActiveModel();
    if (m && m.currency === 'USD') {
      return (costVal || 0) * USD_CNY_RATE;
    }
    return costVal || 0;
  }

  // 总表统计主金额：一律以人民币为主大字显示 (¥X.XX)
  function formatKpiMainCost(model, costVal) {
    const cny = toCnyCost(model, costVal);
    return `¥${cny.toFixed(2)}`;
  }

  // 总表统计副金额：美元为辅（人民币为主，美元为辅）
  function formatKpiSubCost(model, costVal) {
    const m = model || getActiveModel();
    if (m && m.currency === 'USD') {
      return `原价 $${Number(costVal || 0).toFixed(2)} USD (按 1:${USD_CNY_RATE})`;
    } else {
      return `约 $${(Number(costVal || 0) / USD_CNY_RATE).toFixed(2)} USD (按 1:${USD_CNY_RATE})`;
    }
  }

  // 表格单元格费用 (每日日记、每项目表格)：默认人民币单位
  // 对于原计价不是人民币的 (如 USD)，在主金额下方用小字表示原价格相当于多少美金
  function formatLedgerCost(model, costVal) {
    const m = model || getActiveModel();
    const cny = toCnyCost(m, costVal);
    if (m && m.currency === 'USD') {
      return `
        <div class="cost-cny-main">¥${cny.toFixed(2)}</div>
        <div class="cost-usd-sub">($${Number(costVal || 0).toFixed(2)})</div>
      `;
    }
    return `<div class="cost-cny-main">¥${cny.toFixed(2)}</div>`;
  }

  // 内联小计费用 (如日小计、周小计、全景卡片)：主金额为人民币，美元模型尾随小字括号
  function formatInlineCost(model, costVal) {
    const m = model || getActiveModel();
    const cny = toCnyCost(m, costVal);
    if (m && m.currency === 'USD') {
      return `¥${cny.toFixed(2)} <span class="cost-inline-usd">($${Number(costVal || 0).toFixed(2)})</span>`;
    }
    return `¥${cny.toFixed(2)}`;
  }

  // 基础兼容别名
  function formatCost(model, costVal) {
    return formatInlineCost(model, costVal);
  }

  function formatTime(isoStr) {
    if (!isoStr) return '--';
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      const now = new Date();
      const diffSec = Math.floor((now.getTime() - d.getTime()) / 1000);
      if (diffSec < 60) return '刚刚';
      if (diffSec < 3600) return `${Math.floor(diffSec / 60)} 分钟前`;
      if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} 小时前`;
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    } catch (_) {
      return isoStr;
    }
  }

  function showToast(msg) {
    el.toast.textContent = msg;
    el.toast.classList.add('show');
    setTimeout(() => {
      el.toast.classList.remove('show');
    }, 2200);
  }

  function copyToClipboard(text, label) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        showToast(`已复制 ${label || ''}: ${text}`);
      }).catch(() => {
        promptCopy(text);
      });
    } else {
      promptCopy(text);
    }
  }

  function promptCopy(text) {
    const input = document.createElement('input');
    input.value = text;
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    document.body.removeChild(input);
    showToast(`已复制: ${text}`);
  }

  // 初始化与事件绑定
  function init() {
    // 恢复主题偏好
    const savedTheme = localStorage.getItem('myccusage_theme');
    if (savedTheme === 'light') {
      setTheme(false);
    }

    // 恢复计价模型偏好 (记住上一次的选择)
    const savedPricing = localStorage.getItem('myccusage_pricing_model');
    const allModels = getAllPricingModels();
    if (savedPricing && allModels[savedPricing]) {
      setPricingModel(savedPricing, false);
    } else {
      setPricingModel('deepseek-v4.1-flash', false);
    }

    // 渲染下拉菜单
    renderPricingDropdownMenu();

    // Web 端默认倒序时间文本
    if (el.btnSortTime) {
      el.btnSortTime.textContent = '时间倒序 (最新在顶)';
    }

    // 启动心跳保活与页面关闭联动退出机制
    startHeartbeat();

    // 同步导航药丸按钮与 state.agent 状态
    if (el.agentSelector) {
      const activeBtn = el.agentSelector.querySelector(`.segment-btn[data-agent="${state.agent}"]`);
      if (activeBtn) {
        el.agentSelector.querySelectorAll('.segment-btn').forEach(b => b.classList.remove('active'));
        activeBtn.classList.add('active');
      }
    }

    bindEvents();
    checkSyncStatus();
    loadData();
  }

  // 心跳保活与自动退出联动机制
  function startHeartbeat() {
    const sendPing = () => {
      fetch('/api/ping', { method: 'GET', cache: 'no-store' }).catch(() => {});
    };
    sendPing();
    setInterval(sendPing, 2500);

    window.addEventListener('beforeunload', () => {
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/leave');
      }
    });
  }

  // 渲染计价模型下拉菜单
  function renderPricingDropdownMenu() {
    if (!el.pricingOptionsList) return;
    const allModels = getAllPricingModels();
    const currentId = state.pricingModel;

    let html = '';
    Object.values(allModels).forEach(m => {
      const isActive = m.id === currentId;
      html += `
        <div class="pricing-option ${isActive ? 'active' : ''}" data-model="${m.id}">
          <div class="option-row">
            <span class="option-name">${escapeHtml(m.name)}</span>
            <span class="option-check" style="display: ${isActive ? 'inline' : 'none'};">✓</span>
          </div>
        </div>
      `;
    });

    el.pricingOptionsList.innerHTML = html;

    // 绑定鼠标悬停右侧展开该模型计费规则卡片（彻底解决滚动列表 overflow-y 导致的横向截断）
    el.pricingOptionsList.querySelectorAll('.pricing-option').forEach(item => {
      const modelId = item.getAttribute('data-model');
      const m = allModels[modelId];

      item.addEventListener('mouseenter', () => {
        if (!m || !el.pricingFloatingPopover) return;
        const sym = m.currency === 'USD' ? '$' : '¥';
        el.pricingFloatingPopover.innerHTML = `
          <div class="popover-header">
            <strong>${escapeHtml(m.name)}</strong>
            <span class="popover-badge">${m.isBuiltin ? (m.badge || '官方预设') : '自定义模型'}</span>
          </div>
          <div class="popover-rule-list">
            <div class="popover-rule-item">
              <span class="rule-tag tag-input">输入未命中</span>
              <span class="rule-price">${sym} ${formatRate(m.inputRate)} / 1M</span>
            </div>
            <div class="popover-rule-item">
              <span class="rule-tag tag-cache">KV 缓存命中</span>
              <span class="rule-price">${sym} ${formatRate(m.cacheRate)} / 1M</span>
            </div>
            <div class="popover-rule-item">
              <span class="rule-tag tag-output">输出 + 思维链</span>
              <span class="rule-price">${sym} ${formatRate(m.outputRate)} / 1M</span>
            </div>
          </div>
          <div class="popover-desc">
            ${escapeHtml(m.note || '按 Total = Input + Cache + Output 守恒精确折算')}
          </div>
        `;

        if (el.pricingMenu) {
          const itemRect = item.getBoundingClientRect();
          const menuRect = el.pricingMenu.getBoundingClientRect();
          const topOffset = itemRect.top - menuRect.top;
          el.pricingFloatingPopover.style.top = `${Math.max(0, topOffset)}px`;
        }
        el.pricingFloatingPopover.classList.add('visible');
      });
    });

    el.pricingOptionsList.addEventListener('mouseleave', () => {
      if (el.pricingFloatingPopover) el.pricingFloatingPopover.classList.remove('visible');
    });

    el.pricingOptionsList.addEventListener('scroll', () => {
      if (el.pricingFloatingPopover) el.pricingFloatingPopover.classList.remove('visible');
    });
  }

  // 统一计价响应调度中心：模型切换或费率更新后，全局同步刷新当前激活视图的所有价格展示
  function updateAllPricingDisplays() {
    if (state.agent === 'all') {
      if (state.allAgentsData) {
        renderAllAgentsOverview(state.allAgentsData);
      }
    } else {
      if (state.data) {
        renderDashboard(state.data);
      }
    }
  }

  function setPricingModel(modelId, notify = false) {
    const allModels = getAllPricingModels();
    if (!allModels[modelId]) {
      modelId = 'deepseek-v4.1-flash';
    }
    state.pricingModel = modelId;
    localStorage.setItem('myccusage_pricing_model', modelId);
    const model = allModels[modelId];

    if (el.selectedPricingName) {
      el.selectedPricingName.textContent = model.name;
    }

    renderPricingDropdownMenu();

    if (notify) {
      showToast(`已选择计价模型: ${model.name}`);
    }

    // 动态全站重算 (即时响应，调度计价中心)
    updateAllPricingDisplays();
  }

  // ------------------------------------------------------------------------
  // 多端 Git 私有同步模块 (Multi-Device Git Sync)
  // ------------------------------------------------------------------------
  async function checkSyncStatus() {
    try {
      const res = await fetch('/api/sync/status', { cache: 'no-store' });
      if (!res.ok) return;
      const data = await res.json();
      state.syncState = data;
      if (el.btnSync) {
        if (data.enabled) {
          el.btnSync.classList.add('sync-active');
          const devCount = (data.syncedDevices || []).length;
          el.btnSync.title = `多端 Git 同步已就绪 (已连接 ${devCount} 台异机)\n点击立即同步增量，长按或右键打开设置`;
        } else {
          el.btnSync.classList.remove('sync-active');
          el.btnSync.title = `多端 Git 私有同步 (未配置，点击开启)`;
        }
      }
    } catch (_) {}
  }

  let userManuallyEditedId = false;

  function updateGeneratedDeviceId(name) {
    if (!el.syncDeviceId || userManuallyEditedId) return;
    const raw = (name || '').trim().toLowerCase();
    let slug = raw.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    const isMac = navigator.platform ? navigator.platform.toLowerCase().includes('mac') : true;
    const plat = isMac ? 'mac' : (navigator.platform.toLowerCase().includes('win') ? 'win' : 'linux');
    if (!slug) {
      let hash = 0;
      for (let i = 0; i < raw.length; i++) {
        hash = ((hash << 5) - hash) + raw.charCodeAt(i);
        hash |= 0;
      }
      slug = 'dev-' + Math.abs(hash).toString(36).slice(0, 5);
    }
    if (!slug.endsWith(`-${plat}`)) {
      slug = `${slug}-${plat}`;
    }
    el.syncDeviceId.value = slug;
  }

  function openSyncModal(forceSetup = false) {
    if (!el.syncModal) return;
    const isConfigured = state.syncState && state.syncState.enabled && !forceSetup;

    if (!isConfigured) {
      userManuallyEditedId = false;
      if (el.syncSetupView) el.syncSetupView.style.display = 'block';
      if (el.syncManageView) el.syncManageView.style.display = 'none';
      if (el.syncRepoUrl) el.syncRepoUrl.value = state.syncState?.repoUrl || '';
      const defaultName = state.syncState?.deviceName || 'MacBook Air';
      if (el.syncDeviceName) el.syncDeviceName.value = defaultName;
      updateGeneratedDeviceId(defaultName);
    } else {
      if (el.syncSetupView) el.syncSetupView.style.display = 'none';
      if (el.syncManageView) el.syncManageView.style.display = 'block';

      if (el.syncCurrentDeviceDisplay) {
        el.syncCurrentDeviceDisplay.textContent = `${state.syncState.deviceName || '--'} [${state.syncState.deviceId || '--'}]`;
      }
      if (el.syncRepoUrlDisplay) {
        el.syncRepoUrlDisplay.textContent = state.syncState.repoUrl || '--';
        el.syncRepoUrlDisplay.title = state.syncState.repoUrl || '';
      }
      if (el.syncLastTime) {
        el.syncLastTime.textContent = state.syncState.lastSyncTime
          ? `上次同步: ${formatTime(state.syncState.lastSyncTime)}`
          : '上次同步: 从未';
      }

      const devices = state.syncState.syncedDevices || [];
      if (el.syncDeviceCount) el.syncDeviceCount.textContent = String(devices.length);
      if (el.syncDeviceList) {
        if (!devices.length) {
          el.syncDeviceList.innerHTML = `<div class="empty-state" style="padding: 14px; font-size: 0.8rem; color: var(--text-muted); text-align: center;">暂无其他异机设备，另一台电脑绑定同一仓库后同步即可互通</div>`;
        } else {
          el.syncDeviceList.innerHTML = devices.map(d => `
            <div class="sync-device-card">
              <div class="sync-device-name">
                <span>💻</span>
                <span>${escapeHtml(d.deviceName || d.deviceId)}</span>
                <span class="badge badge-subtle" style="font-size: 0.7rem;">${escapeHtml(d.platform || 'remote')}</span>
              </div>
              <div class="sync-device-time">
                ${d.exportedAt ? `活跃于 ${formatTime(d.exportedAt)}` : '已连接'}
              </div>
            </div>
          `).join('');
        }
      }
    }

    el.syncModal.style.display = 'flex';
  }

  function closeSyncModal() {
    if (el.syncModal) el.syncModal.style.display = 'none';
  }

  let syncPopoverAutoCloseTimer = null;

  function openSyncPopover() {
    if (syncPopoverAutoCloseTimer) {
      clearTimeout(syncPopoverAutoCloseTimer);
      syncPopoverAutoCloseTimer = null;
    }
    if (el.syncPopover) {
      el.syncPopover.style.display = 'block';
    }
  }

  function closeSyncPopover() {
    if (syncPopoverAutoCloseTimer) {
      clearTimeout(syncPopoverAutoCloseTimer);
      syncPopoverAutoCloseTimer = null;
    }
    if (el.syncPopover) {
      el.syncPopover.style.display = 'none';
    }
  }

  function resetSyncPopover() {
    openSyncPopover();
    if (el.syncPopoverTitle) el.syncPopoverTitle.textContent = '多端同步进行中...';
    if (el.syncPopoverDot) {
      el.syncPopoverDot.style.backgroundColor = 'var(--accent-blue)';
      el.syncPopoverDot.style.animation = 'pulse 1.8s infinite';
    }
    if (el.syncPopoverError) el.syncPopoverError.style.display = 'none';

    const steps = [
      { id: 'pull', detail: '等待中...' },
      { id: 'export', detail: '增量吸收保护' },
      { id: 'commit', detail: '原子化存储' },
      { id: 'push', detail: '安全增量上云' },
      { id: 'merge', detail: '内存微秒就绪' }
    ];

    steps.forEach(s => {
      const item = document.getElementById(`syncStep_${s.id}`);
      const icon = document.getElementById(`syncStepIcon_${s.id}`);
      const detail = document.getElementById(`syncStepDetail_${s.id}`);
      const badge = document.getElementById(`syncStepBadge_${s.id}`);
      if (item) item.className = 'sync-step-item';
      if (icon) icon.textContent = '⚪';
      if (detail) detail.textContent = s.detail;
      if (badge) badge.textContent = '等待';
    });
  }

  function updateSyncStep(stepId, status, message, detail) {
    openSyncPopover();
    const item = document.getElementById(`syncStep_${stepId}`);
    const icon = document.getElementById(`syncStepIcon_${stepId}`);
    const detailEl = document.getElementById(`syncStepDetail_${stepId}`);
    const badge = document.getElementById(`syncStepBadge_${stepId}`);

    if (item) {
      item.className = `sync-step-item ${status}`;
    }

    if (status === 'running') {
      if (icon) icon.textContent = '⏳';
      if (badge) badge.textContent = '进行中';
      if (detailEl) detailEl.textContent = message || detail || '正在执行...';
    } else if (status === 'done') {
      if (icon) icon.textContent = '✅';
      if (badge) badge.textContent = '已完成';
      if (detailEl) detailEl.textContent = message || detail || '完成';
    } else if (status === 'error') {
      if (icon) icon.textContent = '❌';
      if (badge) badge.textContent = '失败';
      if (detailEl) detailEl.textContent = message || detail || '异常中断';
      if (el.syncPopoverTitle) el.syncPopoverTitle.textContent = '❌ 同步失败';
      if (el.syncPopoverDot) {
        el.syncPopoverDot.style.backgroundColor = '#ef4444';
        el.syncPopoverDot.style.animation = 'none';
      }
      if (el.syncPopoverError && el.syncPopoverErrorMsg) {
        el.syncPopoverErrorMsg.textContent = detail || message || '未知网络或 Git 错误';
        el.syncPopoverError.style.display = 'block';
      }
    }

    if (stepId === 'finish') {
      if (status === 'done') {
        if (el.syncPopoverTitle) el.syncPopoverTitle.textContent = '🎉 同步全部完成！';
        if (el.syncPopoverDot) {
          el.syncPopoverDot.style.backgroundColor = 'var(--accent-green)';
          el.syncPopoverDot.style.animation = 'none';
        }
        syncPopoverAutoCloseTimer = setTimeout(() => {
          closeSyncPopover();
        }, 4000);
      } else if (status === 'error') {
        if (el.syncPopoverTitle) el.syncPopoverTitle.textContent = '❌ 同步中断';
        if (el.syncPopoverDot) {
          el.syncPopoverDot.style.backgroundColor = '#ef4444';
          el.syncPopoverDot.style.animation = 'none';
        }
        if (el.syncPopoverError && el.syncPopoverErrorMsg) {
          el.syncPopoverErrorMsg.textContent = detail || message || '发生错误';
          el.syncPopoverError.style.display = 'block';
        }
      }
    }
  }

  let _isSyncing = false;

  async function triggerSyncAction() {
    if (!el.btnSync) return;
    if (_isSyncing) return; // 已在同步中，忽略重复点击
    _isSyncing = true;
    el.btnSync.classList.add('syncing');
    if (el.syncBtnText) el.syncBtnText.textContent = '同步中...';
    if (el.btnTriggerModalSync) {
      el.btnTriggerModalSync.disabled = true;
      el.btnTriggerModalSync.textContent = '🔄 正在同步...';
    }

    resetSyncPopover();

    let hasError = false;
    let finishData = null;

    try {
      const res = await fetch('/api/sync/trigger?stream=1', {
        method: 'POST',
        headers: { 'Accept': 'text/event-stream' }
      });

      if (!res.ok) {
        let errText = `HTTP ${res.status}`;
        try {
          const errJson = await res.json();
          if (errJson.error) errText = errJson.error;
        } catch (_) {}
        throw new Error(errText);
      }

      if (res.body && res.body.getReader) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop(); // 保留不完整行

          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('data:')) {
              try {
                const payload = JSON.parse(trimmed.slice(5).trim());
                updateSyncStep(payload.step, payload.status, payload.message, payload.detail);
                if (payload.status === 'error') {
                  hasError = true;
                }
                if (payload.step === 'finish' && payload.detail) {
                  try { finishData = JSON.parse(payload.detail); } catch (_) {}
                }
              } catch (_) {}
            }
          }
        }
      } else {
        const data = await res.json();
        finishData = data;
        updateSyncStep('finish', 'done', `多端同步完成！(耗时 ${data.duration}s)`);
      }

      if (hasError) {
        showToast('❌ 同步存在异常，请查看气泡提示');
      } else {
        const dur = finishData?.duration ? `(耗时 ${finishData.duration}s)` : '';
        showToast(`🎉 多端同步成功！${dur}`);
      }

      await checkSyncStatus();
      if (el.syncModal && el.syncModal.style.display !== 'none') {
        openSyncModal();
      }
      // 用项目原生 /api/refresh 强制穿透服务端缓存重算，再渲染最新数据
      try { await fetch(`/api/refresh?agent=${state.agent === 'all' ? 'all' : state.agent}`, { method: 'POST' }); } catch (_) {}
      await loadData();
    } catch (err) {
      updateSyncStep('finish', 'error', '同步异常失败', err.message);
      showToast(`❌ 同步失败: ${err.message}`);
    } finally {
      // 始终恢复按钮状态，无论成功/失败/网络异常均可重试
      _isSyncing = false;
      el.btnSync.classList.remove('syncing');
      if (el.syncBtnText) el.syncBtnText.textContent = '同步';
      if (el.btnTriggerModalSync) {
        el.btnTriggerModalSync.disabled = false;
        el.btnTriggerModalSync.textContent = '🔄 立即同步增量';
      }
    }
  }

  async function confirmSyncSetup() {
    const repoUrl = el.syncRepoUrl ? el.syncRepoUrl.value.trim() : '';
    const deviceName = el.syncDeviceName ? el.syncDeviceName.value.trim() : '';
    const deviceId = el.syncDeviceId ? el.syncDeviceId.value.trim() : '';

    if (!repoUrl) {
      showToast('❌ 请输入私有 Git 仓库地址');
      if (el.syncRepoUrl) el.syncRepoUrl.focus();
      return;
    }

    if (el.btnConfirmSyncSetup) {
      el.btnConfirmSyncSetup.disabled = true;
      el.btnConfirmSyncSetup.innerHTML = '<span>🔗 正在克隆并连接 (约需几秒)...</span>';
    }

    try {
      const res = await fetch('/api/sync/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repoUrl, deviceName, deviceId })
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        throw new Error(data.error || '连接仓库失败');
      }
      showToast('🎉 成功连接多端同步仓库！已生成并推送首次用量快照');
      closeSyncModal();
      await checkSyncStatus();
      await loadData();
    } catch (err) {
      showToast(`❌ 初始化同步仓库失败: ${err.message}`);
    } finally {
      if (el.btnConfirmSyncSetup) {
        el.btnConfirmSyncSetup.disabled = false;
        el.btnConfirmSyncSetup.innerHTML = '<span>🔗 连接并同步首次数据</span>';
      }
    }
  }

  async function unbindSync() {
    if (!confirm('确认解除当前多端同步仓库绑定吗？\n本地已拉取的历史账本不会被删除，但将不再自动同步更新。')) {
      return;
    }
    try {
      const res = await fetch('/api/sync/unbind', { method: 'POST' });
      if (!res.ok) throw new Error('解除绑定失败');
      showToast('已解除多端同步绑定');
      closeSyncModal();
      await checkSyncStatus();
      await loadData();
    } catch (err) {
      showToast(`❌ 操作失败: ${err.message}`);
    }
  }

  // ------------------------------------------------------------------------
  // 计费模型管理弹窗 (二级)
  // ------------------------------------------------------------------------
  function openModelManager() {
    state.managingModelId = state.pricingModel;
    renderManagerModelList();
    renderManagerDetail(state.managingModelId);
    el.modelManagerModal.style.display = 'flex';
  }

  function closeModelManager() {
    el.modelManagerModal.style.display = 'none';
  }

  function renderManagerModelList() {
    const all = getAllPricingModels();
    const count = Object.keys(all).length;
    if (el.modelCountBadge) el.modelCountBadge.textContent = `${count} 款`;

    let html = '';
    Object.values(all).forEach(m => {
      const isSelected = m.id === state.managingModelId;
      const isActiveInDashboard = m.id === state.pricingModel;
      const sym = m.currency === 'USD' ? '$' : '¥';
      html += `
        <div class="model-list-item ${isSelected ? 'active' : ''}" data-id="${m.id}">
          <div class="model-item-title-row">
            <span class="model-item-name" title="${escapeHtml(m.name)}">${escapeHtml(m.name)}</span>
            <div style="display:flex; align-items:center; gap:4px;">
              ${isActiveInDashboard ? `<span class="badge badge-green" style="font-size:0.65rem; padding:1px 4px;">当前使用</span>` : ''}
              <span class="badge ${m.isBuiltin ? 'badge-blue' : 'badge-purple'}" style="font-size:0.65rem; padding:1px 4px;">
                ${m.isBuiltin ? '预设' : '自定义'}
              </span>
            </div>
          </div>
          <div class="model-item-rates">
            <span>入: ${sym}${formatRate(m.inputRate)}</span>
            <span>缓: ${sym}${formatRate(m.cacheRate)}</span>
            <span>出: ${sym}${formatRate(m.outputRate)}</span>
          </div>
        </div>
      `;
    });
    el.manageModelList.innerHTML = html;

    el.manageModelList.querySelectorAll('.model-list-item').forEach(item => {
      item.addEventListener('click', () => {
        const id = item.getAttribute('data-id');
        renderManagerDetail(id);
      });
    });
  }

  function renderManagerDetail(modelId) {
    const all = getAllPricingModels();
    const m = all[modelId] || Object.values(all)[0] || DEFAULT_PRICING_MODELS['deepseek-v4.1-flash'];
    state.managingModelId = m.id;

    el.manageModelList.querySelectorAll('.model-list-item').forEach(it => {
      it.classList.toggle('active', it.getAttribute('data-id') === m.id);
    });

    el.detailModelTitle.textContent = m.name;
    el.detailModelBadge.textContent = m.isBuiltin ? (m.isModified ? '预设 (已修改)' : '预设模型') : '自定义模型';
    el.detailModelBadge.className = `badge ${m.isBuiltin ? 'badge-blue' : 'badge-purple'}`;

    el.editModelName.value = m.name;
    el.editModelCurrency.value = m.currency || 'CNY';
    updateCurrencySymbols(m.currency || 'CNY');

    el.editModelInput.value = m.inputRate;
    el.editModelCache.value = m.cacheRate;
    el.editModelOutput.value = m.outputRate;
    el.editModelNote.value = m.note || '';

    // 用户可自由修改和删除任何模型（包括系统默认模型）
    el.editModelName.disabled = false;
    el.editModelCurrency.disabled = false;
    el.editModelInput.disabled = false;
    el.editModelCache.disabled = false;
    el.editModelOutput.disabled = false;
    el.editModelNote.disabled = false;
    el.btnSaveModelEdit.disabled = false;
    el.btnDeleteModel.disabled = false;
    el.btnDeleteModel.title = '删除此模型';

    const isAlreadyActive = m.id === state.pricingModel;
    el.btnApplySelectedModel.disabled = isAlreadyActive;
    el.btnApplySelectedModel.textContent = isAlreadyActive ? '✓ 当前已在使用' : '设为当前使用';
  }

  function updateCurrencySymbols(currency) {
    const sym = currency === 'USD' ? '$' : '¥';
    if (el.symbolInputRate) el.symbolInputRate.textContent = sym;
    if (el.symbolCacheRate) el.symbolCacheRate.textContent = sym;
    if (el.symbolOutputRate) el.symbolOutputRate.textContent = sym;
  }

  function saveModelEdit() {
    const all = getAllPricingModels();
    const currentId = state.managingModelId;
    const existing = all[currentId];
    if (!existing) {
      showToast('⚠️ 未找到要修改的模型');
      return;
    }

    const name = el.editModelName.value.trim();
    const currency = el.editModelCurrency.value;
    const inputRate = parseFloat(el.editModelInput.value);
    const cacheRate = parseFloat(el.editModelCache.value);
    const outputRate = parseFloat(el.editModelOutput.value);
    const note = el.editModelNote.value.trim();

    if (!name) {
      showToast('❌ 模型名称不能为空');
      return;
    }
    if (isNaN(inputRate) || inputRate < 0 || isNaN(cacheRate) || cacheRate < 0 || isNaN(outputRate) || outputRate < 0) {
      showToast('❌ 费率必须为大于等于 0 的有效数字');
      return;
    }

    const customModels = getCustomModels();
    const updatedModel = Object.assign({}, existing, {
      name,
      currency,
      inputRate,
      cacheRate,
      outputRate,
      note,
      isModified: true
    });

    customModels[currentId] = updatedModel;
    saveCustomModels(customModels);

    renderManagerModelList();
    renderManagerDetail(currentId);
    renderPricingDropdownMenu();

    if (state.pricingModel === currentId) {
      el.selectedPricingName.textContent = updatedModel.name;
      updateAllPricingDisplays();
    }

    showToast(`✅ 已保存模型修改: ${updatedModel.name}`);
  }

  function deleteCurrentModel() {
    const all = getAllPricingModels();
    const currentId = state.managingModelId;
    const m = all[currentId];
    if (!m) {
      showToast('⚠️ 未找到要删除的模型');
      return;
    }

    if (Object.keys(all).length <= 1) {
      showToast('⚠️ 至少保留一款计费模型，无法删除全部');
      return;
    }

    if (!confirm(`确定要彻底删除模型「${m.name}」吗？删除后可在右上角重置恢复预设。`)) {
      return;
    }

    // 从自定义中删除（如果有）
    const customModels = getCustomModels();
    delete customModels[currentId];
    saveCustomModels(customModels);

    // 记录到已删除集合
    const deletedIds = getDeletedModelIds();
    if (!deletedIds.includes(currentId)) {
      deletedIds.push(currentId);
      saveDeletedModelIds(deletedIds);
    }

    // 挑选剩余有效模型
    const remaining = getAllPricingModels();
    const nextModelId = Object.keys(remaining)[0];

    if (state.pricingModel === currentId) {
      setPricingModel(nextModelId, false);
    }

    state.managingModelId = nextModelId;
    renderManagerModelList();
    renderManagerDetail(nextModelId);
    renderPricingDropdownMenu();
    showToast(`已删除模型: ${m.name}`);
  }

  function resetAllDefaultModels() {
    if (!confirm('确定要重置所有系统预设模型并恢复被删除的默认模型吗？（自定义导入的模型将保留）')) {
      return;
    }
    // 清除已删除列表
    saveDeletedModelIds([]);
    // 清除对预设模型的覆写
    const customModels = getCustomModels();
    Object.keys(DEFAULT_PRICING_MODELS).forEach(id => {
      delete customModels[id];
    });
    saveCustomModels(customModels);

    renderManagerModelList();
    const active = getActiveModel();
    renderManagerDetail(active.id);
    renderPricingDropdownMenu();
    updateAllPricingDisplays();
    showToast('✨ 已恢复所有系统默认预设模型');
  }

  // ------------------------------------------------------------------------
  // 智能导入 / 新增模型弹窗 (三级) & 高容错解析器
  // ------------------------------------------------------------------------
  function openAddModelModal() {
    el.importConfigText.value = '';
    resetParsePreview();
    el.addModelModal.style.display = 'flex';
    setTimeout(() => {
      el.importConfigText.focus();
    }, 100);
  }

  function closeAddModelModal() {
    el.addModelModal.style.display = 'none';
  }

  function resetParsePreview() {
    el.parseStatusBar.className = 'parse-status-bar';
    el.parseStatusBar.innerHTML = `<span class="status-indicator">⚪ 请输入或粘贴模型配置文本</span>`;
    const details = el.importPreviewContainer.querySelector('.parse-preview-details');
    if (details) details.remove();
    el.btnConfirmImportModel.disabled = true;
    parsedImportModel = null;
  }

  let parsedImportModel = null;

  function parsePricingConfig(rawText) {
    if (!rawText || !rawText.trim()) {
      return { valid: false, errors: ['请输入或粘贴模型配置文本'] };
    }

    let text = rawText.trim();
    // 自动剥离 Markdown 代码块标记（如 ```pricing ... ``` 或 ```yaml ... ``` 或 ```json ... ```）
    text = text.replace(/^```[a-zA-Z0-9_-]*\s*\n?/m, '').replace(/\n?```\s*$/m, '').trim();

    // 尝试直接作为 JSON 解析
    if (text.startsWith('{') && text.endsWith('}')) {
      try {
        const obj = JSON.parse(text);
        const name = (obj.name || obj.model || obj.title || '').trim();
        let currency = (obj.currency || obj.unit || 'CNY').toUpperCase();
        if (currency.includes('$') || currency.includes('USD')) currency = 'USD';
        else currency = 'CNY';

        const inputRate = parseFloat(obj.input || obj.inputRate || obj.input_rate);
        const cacheRate = parseFloat(obj.cache || obj.cacheRate || obj.cache_hit);
        const outputRate = parseFloat(obj.output || obj.outputRate || obj.output_rate);
        const note = (obj.note || obj.desc || obj.description || '').trim();

        const errors = [];
        if (!name) errors.push('缺少模型名称 (name)');
        if (isNaN(inputRate) || inputRate < 0) errors.push('输入未命中价格 (inputRate) 无效');
        if (isNaN(cacheRate) || cacheRate < 0) errors.push('缓存命中价格 (cacheRate) 无效');
        if (isNaN(outputRate) || outputRate < 0) errors.push('输出单价 (outputRate) 无效');

        if (errors.length > 0) {
          return { valid: false, errors };
        }
        return {
          valid: true,
          model: {
            name,
            currency,
            inputRate,
            cacheRate,
            outputRate,
            note: note || `官方计费标准 (输入 ${currency === 'USD' ? '$' : '¥'}${inputRate}/M | 缓存 ${currency === 'USD' ? '$' : '¥'}${cacheRate}/M | 输出 ${currency === 'USD' ? '$' : '¥'}${outputRate}/M)`
          }
        };
      } catch (e) {}
    }

    // 键值对逐行解析
    const lines = text.split('\n');
    const parsed = {};

    function extractFirstNum(str) {
      if (!str) return NaN;
      const match = str.match(/([0-9]+(?:\.[0-9]+)?)/);
      return match ? parseFloat(match[1]) : NaN;
    }

    lines.forEach(line => {
      line = line.trim();
      if (!line || line.startsWith('#') || line.startsWith('//')) return;

      const sepIdx = line.indexOf(':') !== -1 ? line.indexOf(':') : line.indexOf('：');
      if (sepIdx === -1) return;

      const key = line.slice(0, sepIdx).trim().toLowerCase();
      const val = line.slice(sepIdx + 1).trim();

      if (['name', 'model', '模型', '模型名', '模型名称', '名称', 'title'].includes(key)) {
        parsed.name = val;
      } else if (['currency', '货币', '单位', '币种', 'unit'].includes(key)) {
        if (val.toUpperCase().includes('USD') || val.includes('$') || val.includes('美元')) {
          parsed.currency = 'USD';
        } else {
          parsed.currency = 'CNY';
        }
      } else if (['input', 'inputrate', 'input_rate', '输入', '输入价格', '输入未命中', '输入未命中价格', '未命中'].includes(key)) {
        parsed.inputRate = extractFirstNum(val);
        if (val.includes('$') && !parsed.currency) parsed.currency = 'USD';
      } else if (['cache', 'cacherate', 'cache_rate', 'cache_hit', '缓存', '缓存命中', '缓存命中价格', '缓存单价', '命中'].includes(key)) {
        parsed.cacheRate = extractFirstNum(val);
      } else if (['output', 'outputrate', 'output_rate', '输出', '输出价格', '思考与输出', '思维链', '输出单价'].includes(key)) {
        parsed.outputRate = extractFirstNum(val);
      } else if (['note', 'desc', 'description', '备注', '说明', '场景'].includes(key)) {
        parsed.note = val;
      }
    });

    const errors = [];
    if (!parsed.name || !parsed.name.trim()) {
      errors.push('缺少模型名称 (name)');
    }
    if (parsed.inputRate === undefined || isNaN(parsed.inputRate) || parsed.inputRate < 0) {
      errors.push('缺少或无效的输入价格 (input)');
    }
    if (parsed.cacheRate === undefined || isNaN(parsed.cacheRate) || parsed.cacheRate < 0) {
      errors.push('缺少或无效的缓存命中价格 (cache)');
    }
    if (parsed.outputRate === undefined || isNaN(parsed.outputRate) || parsed.outputRate < 0) {
      errors.push('缺少或无效的输出价格 (output)');
    }

    if (errors.length > 0) {
      return { valid: false, errors };
    }

    const currency = parsed.currency || 'CNY';
    const sym = currency === 'USD' ? '$' : '¥';
    return {
      valid: true,
      model: {
        name: parsed.name.trim(),
        currency: currency,
        inputRate: parsed.inputRate,
        cacheRate: parsed.cacheRate,
        outputRate: parsed.outputRate,
        note: parsed.note ? parsed.note.trim() : `官方计费标准 (输入 ${sym}${parsed.inputRate}/M | 缓存 ${sym}${parsed.cacheRate}/M | 输出 ${sym}${parsed.outputRate}/M)`
      }
    };
  }

  function handleImportTextChange() {
    const text = el.importConfigText.value;
    if (!text || !text.trim()) {
      resetParsePreview();
      return;
    }

    const res = parsePricingConfig(text);
    if (!res.valid) {
      parsedImportModel = null;
      el.btnConfirmImportModel.disabled = true;
      el.parseStatusBar.className = 'parse-status-bar error';
      el.parseStatusBar.innerHTML = `<span>❌ 解析错误: ${res.errors.join('；')}</span>`;
      const details = el.importPreviewContainer.querySelector('.parse-preview-details');
      if (details) details.remove();
    } else {
      parsedImportModel = res.model;
      el.btnConfirmImportModel.disabled = false;
      el.parseStatusBar.className = 'parse-status-bar valid';
      el.parseStatusBar.innerHTML = `<span>✅ 格式解析成功: <strong>${escapeHtml(res.model.name)}</strong></span>`;

      const sym = res.model.currency === 'USD' ? '$' : '¥';
      let details = el.importPreviewContainer.querySelector('.parse-preview-details');
      if (!details) {
        details = document.createElement('div');
        details.className = 'parse-preview-details';
        el.importPreviewContainer.appendChild(details);
      }
      details.innerHTML = `
        <div class="preview-tag">
          <span class="preview-tag-label">币种单位</span>
          <span class="preview-tag-val">${res.model.currency} (${sym})</span>
        </div>
        <div class="preview-tag">
          <span class="preview-tag-label">输入未命中</span>
          <span class="preview-tag-val" style="color:var(--color-input);">${sym}${formatRate(res.model.inputRate)}/M</span>
        </div>
        <div class="preview-tag">
          <span class="preview-tag-label">缓存命中</span>
          <span class="preview-tag-val" style="color:var(--color-cache);">${sym}${formatRate(res.model.cacheRate)}/M</span>
        </div>
        <div class="preview-tag">
          <span class="preview-tag-label">输出思考</span>
          <span class="preview-tag-val" style="color:var(--color-output);">${sym}${formatRate(res.model.outputRate)}/M</span>
        </div>
        <div class="preview-tag" style="grid-column: span 2;">
          <span class="preview-tag-label">备注说明</span>
          <span class="preview-tag-val" style="font-size:0.72rem; color:var(--text-muted);">${escapeHtml(res.model.note)}</span>
        </div>
      `;
    }
  }

  function confirmImportModel() {
    if (!parsedImportModel) return;
    const modelId = 'model_' + Date.now();
    const newModel = Object.assign({}, parsedImportModel, {
      id: modelId,
      badge: '自定义',
      isBuiltin: false
    });

    const customModels = getCustomModels();
    customModels[modelId] = newModel;
    saveCustomModels(customModels);

    setPricingModel(modelId, false);

    closeAddModelModal();
    closeModelManager();

    showToast(`🎉 已成功导入并启用模型: ${newModel.name}`);
  }

  function bindEvents() {
    // 计价模型下拉展开/收起
    if (el.pricingTrigger) {
      el.pricingTrigger.addEventListener('click', (e) => {
        e.stopPropagation();
        el.pricingDropdownContainer.classList.toggle('open');
        if (!el.pricingDropdownContainer.classList.contains('open') && el.pricingFloatingPopover) {
          el.pricingFloatingPopover.classList.remove('visible');
        }
      });
    }

    document.addEventListener('click', (e) => {
      if (el.pricingDropdownContainer && !el.pricingDropdownContainer.contains(e.target)) {
        el.pricingDropdownContainer.classList.remove('open');
        if (el.pricingFloatingPopover) el.pricingFloatingPopover.classList.remove('visible');
      }
    });

    // 下拉菜单内点选模型
    if (el.pricingOptionsList) {
      el.pricingOptionsList.addEventListener('click', (e) => {
        const opt = e.target.closest('.pricing-option');
        if (!opt) return;
        const modelId = opt.getAttribute('data-model');
        if (el.pricingFloatingPopover) el.pricingFloatingPopover.classList.remove('visible');
        setPricingModel(modelId, true);
        el.pricingDropdownContainer.classList.remove('open');
      });
    }

    // 下拉顶部管理入口
    if (el.btnOpenModelManager) {
      el.btnOpenModelManager.addEventListener('click', (e) => {
        e.stopPropagation();
        el.pricingDropdownContainer.classList.remove('open');
        openModelManager();
      });
    }

    // 模型管理弹窗操作
    if (el.btnCloseManagerModal) {
      el.btnCloseManagerModal.addEventListener('click', closeModelManager);
    }
    if (el.modelManagerModal) {
      el.modelManagerModal.addEventListener('click', (e) => {
        if (e.target === el.modelManagerModal) closeModelManager();
      });
    }
    if (el.btnOpenAddModelModal) {
      el.btnOpenAddModelModal.addEventListener('click', openAddModelModal);
    }
    if (el.editModelCurrency) {
      el.editModelCurrency.addEventListener('change', () => {
        updateCurrencySymbols(el.editModelCurrency.value);
      });
    }
    if (el.btnApplySelectedModel) {
      el.btnApplySelectedModel.addEventListener('click', () => {
        setPricingModel(state.managingModelId, true);
        renderManagerModelList();
        renderManagerDetail(state.managingModelId);
      });
    }
    if (el.btnSaveModelEdit) {
      el.btnSaveModelEdit.addEventListener('click', saveModelEdit);
    }
    if (el.btnDeleteModel) {
      el.btnDeleteModel.addEventListener('click', deleteCurrentModel);
    }
    if (el.btnResetDefaultModels) {
      el.btnResetDefaultModels.addEventListener('click', resetAllDefaultModels);
    }

    // 智能导入弹窗操作
    if (el.btnCloseAddModal) {
      el.btnCloseAddModal.addEventListener('click', closeAddModelModal);
    }
    if (el.btnCancelAddModal) {
      el.btnCancelAddModal.addEventListener('click', closeAddModelModal);
    }
    if (el.addModelModal) {
      el.addModelModal.addEventListener('click', (e) => {
        if (e.target === el.addModelModal) closeAddModelModal();
      });
    }
    if (el.btnCopyAiPrompt) {
      el.btnCopyAiPrompt.addEventListener('click', () => {
        const promptText = el.aiPromptCodeBox ? el.aiPromptCodeBox.textContent : '';
        copyToClipboard(promptText, 'AI 提示词');
      });
    }
    if (el.btnLoadExample) {
      el.btnLoadExample.addEventListener('click', () => {
        el.importConfigText.value = '```pricing\nname: Claude 3.5 Sonnet\ncurrency: USD\ninput: 3.0\ncache: 0.3\noutput: 15.0\nnote: 官方标准计费 (输入 $3/M | 缓存 $0.3/M | 输出 $15/M)\n```';
        handleImportTextChange();
      });
    }
    if (el.importConfigText) {
      el.importConfigText.addEventListener('input', handleImportTextChange);
    }
    if (el.btnConfirmImportModel) {
      el.btnConfirmImportModel.addEventListener('click', confirmImportModel);
    }

    // 多端 Git 同步按钮与弹窗操作
    if (el.btnSync) {
      el.btnSync.addEventListener('click', (e) => {
        if (!state.syncState || !state.syncState.enabled || e.shiftKey || e.altKey || e.ctrlKey) {
          openSyncModal();
        } else {
          triggerSyncAction();
        }
      });
      el.btnSync.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        openSyncModal();
      });
    }

    if (el.btnSyncSettings) {
      el.btnSyncSettings.addEventListener('click', (e) => {
        e.stopPropagation();
        openSyncModal();
      });
    }

    if (el.btnCloseSyncPopover) {
      el.btnCloseSyncPopover.addEventListener('click', (e) => {
        e.stopPropagation();
        closeSyncPopover();
      });
    }

    document.addEventListener('click', (e) => {
      if (el.syncPopover && el.syncPopover.style.display !== 'none') {
        const wrapper = document.querySelector('.sync-nav-wrapper');
        if (wrapper && !wrapper.contains(e.target)) {
          if (!el.btnSync || !el.btnSync.classList.contains('syncing')) {
            closeSyncPopover();
          }
        }
      }
    });

    if (el.btnCloseSyncModal) el.btnCloseSyncModal.addEventListener('click', closeSyncModal);
    if (el.btnCloseSyncView) el.btnCloseSyncView.addEventListener('click', closeSyncModal);
    if (el.btnCancelSyncSetup) el.btnCancelSyncSetup.addEventListener('click', closeSyncModal);
    if (el.syncModal) {
      el.syncModal.addEventListener('click', (e) => {
        if (e.target === el.syncModal) closeSyncModal();
      });
    }
    if (el.btnConfirmSyncSetup) el.btnConfirmSyncSetup.addEventListener('click', confirmSyncSetup);
    if (el.btnUnbindSync) el.btnUnbindSync.addEventListener('click', unbindSync);
    if (el.btnTriggerModalSync) el.btnTriggerModalSync.addEventListener('click', triggerSyncAction);
    if (el.syncDeviceName) {
      el.syncDeviceName.addEventListener('input', () => {
        updateGeneratedDeviceId(el.syncDeviceName.value);
      });
    }
    if (el.syncDeviceId) {
      el.syncDeviceId.addEventListener('input', () => {
        userManuallyEditedId = true;
      });
    }

    // 切换 Agent
    el.agentSelector.addEventListener('click', (e) => {
      const btn = e.target.closest('.segment-btn');
      if (!btn) return;
      const agent = btn.getAttribute('data-agent');
      if (agent === state.agent) return;

      document.querySelectorAll('.segment-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.agent = agent;
      loadData();
    });

    // 切换模式 (Daily vs Session)
    el.modeSelector.addEventListener('click', (e) => {
      const btn = e.target.closest('.tab-btn');
      if (!btn) return;
      const mode = btn.getAttribute('data-mode');
      if (mode === state.mode) return;

      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.mode = mode;
      loadData();
    });

    // 排序按钮 (点击时间按钮支持在倒序和正序间切换，默认倒序)
    el.btnSortTime.addEventListener('click', () => {
      if (state.sort === 'time') {
        state.timeSortOrder = state.timeSortOrder === 'desc' ? 'asc' : 'desc';
      } else {
        state.sort = 'time';
        state.timeSortOrder = 'desc'; // 重新切回时间排序时优先倒序
      }
      el.btnSortTime.classList.add('active');
      el.btnSortTokens.classList.remove('active');
      el.btnSortTime.textContent = state.timeSortOrder === 'desc' ? '时间倒序 (最新在顶)' : '时间正序 (最新在底)';
      if (state.agent === 'all' && state.allAgentsData) {
        renderAllAgentsOverview(state.allAgentsData);
      } else {
        filterAndRenderLedger();
      }
    });

    el.btnSortTokens.addEventListener('click', () => {
      if (state.sort === 'tokens') return;
      state.sort = 'tokens';
      el.btnSortTokens.classList.add('active');
      el.btnSortTime.classList.remove('active');
      if (state.agent === 'all' && state.allAgentsData) {
        renderAllAgentsOverview(state.allAgentsData);
      } else {
        filterAndRenderLedger();
      }
    });

    // 刷新按钮 (强制刷新今日切片)
    el.btnRefresh.addEventListener('click', () => {
      refreshData();
    });

    // 主题切换
    el.btnThemeToggle.addEventListener('click', () => {
      setTheme(!state.isDarkTheme);
    });

    // 实时搜索
    el.searchInput.addEventListener('input', (e) => {
      state.searchQuery = e.target.value.trim().toLowerCase();
      el.btnClearSearch.style.display = state.searchQuery ? 'block' : 'none';
      filterAndRenderLedger();
    });

    el.btnClearSearch.addEventListener('click', () => {
      el.searchInput.value = '';
      state.searchQuery = '';
      el.btnClearSearch.style.display = 'none';
      filterAndRenderLedger();
    });

    // 全部折叠/展开
    el.btnToggleAllAccordion.addEventListener('click', () => {
      const isExpand = el.btnToggleAllAccordion.textContent.includes('展开');
      const weeks = document.querySelectorAll('.week-card');
      const days = document.querySelectorAll('.day-block');
      weeks.forEach(w => w.classList.toggle('collapsed', !isExpand));
      days.forEach(d => d.classList.toggle('collapsed', !isExpand));
      el.btnToggleAllAccordion.textContent = isExpand ? '收起全部' : '展开全部';
    });

    // 趋势图小组件快速定位回到最近 30 天
    if (el.btnSnapLatest) {
      el.btnSnapLatest.addEventListener('click', () => {
        if (el.trendScrollViewport) {
          const maxScroll = el.trendScrollViewport.scrollWidth - el.trendScrollViewport.clientWidth;
          el.trendScrollViewport.scrollTo({ left: maxScroll, behavior: 'smooth' });
        }
      });
    }

    // 趋势图小组件内部横滑滚动与拖拽监听
    if (el.trendScrollViewport) {
      el.trendScrollViewport.addEventListener('scroll', () => {
        const maxScroll = el.trendScrollViewport.scrollWidth - el.trendScrollViewport.clientWidth;
        const isNearEnd = (maxScroll - el.trendScrollViewport.scrollLeft) < 35;
        if (el.btnSnapLatest) {
          el.btnSnapLatest.style.display = isNearEnd ? 'none' : 'inline-flex';
        }
        if (el.trendScrollHintText && maxScroll > 0) {
          if (isNearEnd) {
            el.trendScrollHintText.textContent = `📅 默认展示近 30 天 · 可向左横滑查看更早历史`;
          } else {
            el.trendScrollHintText.textContent = `⏳ 历史数据查看中 · 可点击右侧快速返回`;
          }
        }
      });

      // 鼠标按住拖拽滑动 (Drag to scroll)
      let isMouseDown = false;
      let startMouseX = 0;
      let startScrollLeft = 0;

      el.trendScrollViewport.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        isMouseDown = true;
        el.trendScrollViewport.classList.add('grabbing');
        startMouseX = e.pageX - el.trendScrollViewport.offsetLeft;
        startScrollLeft = el.trendScrollViewport.scrollLeft;
      });

      window.addEventListener('mouseup', () => {
        if (isMouseDown) {
          isMouseDown = false;
          if (el.trendScrollViewport) el.trendScrollViewport.classList.remove('grabbing');
        }
      });

      el.trendScrollViewport.addEventListener('mousemove', (e) => {
        if (!isMouseDown) return;
        e.preventDefault();
        const currentX = e.pageX - el.trendScrollViewport.offsetLeft;
        const walk = (currentX - startMouseX) * 1.5;
        el.trendScrollViewport.scrollLeft = startScrollLeft - walk;
      });
    }

    // 竞赛折线图时间范围切换
    if (el.raceRangeSelector) {
      el.raceRangeSelector.querySelectorAll('.race-range-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          el.raceRangeSelector.querySelectorAll('.race-range-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          state.raceRange = btn.getAttribute('data-range') || '30';
          if (state.allAgentsData) {
            renderRaceChart(state.allAgentsData);
          }
        });
      });
    }

    // 竞赛折线图内部横滑鼠标拖拽
    if (el.raceScrollViewport) {
      let isRaceMouseDown = false;
      let startRaceMouseX = 0;
      let startRaceScrollLeft = 0;

      el.raceScrollViewport.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        isRaceMouseDown = true;
        el.raceScrollViewport.classList.add('grabbing');
        startRaceMouseX = e.pageX - el.raceScrollViewport.offsetLeft;
        startRaceScrollLeft = el.raceScrollViewport.scrollLeft;
      });

      window.addEventListener('mouseup', () => {
        if (isRaceMouseDown) {
          isRaceMouseDown = false;
          if (el.raceScrollViewport) el.raceScrollViewport.classList.remove('grabbing');
        }
      });

      el.raceScrollViewport.addEventListener('mousemove', (e) => {
        if (!isRaceMouseDown) return;
        e.preventDefault();
        const currentX = e.pageX - el.raceScrollViewport.offsetLeft;
        const walk = (currentX - startRaceMouseX) * 1.5;
        el.raceScrollViewport.scrollLeft = startRaceScrollLeft - walk;
      });
    }

    // 窗口尺寸变化自适应重绘
    window.addEventListener('resize', () => {
      clearTimeout(window._trendResizeTimer);
      window._trendResizeTimer = setTimeout(() => {
        if (state.agent === 'all' && state.allAgentsData) {
          renderCharts(state.allAgentsData);
          renderRaceChart(state.allAgentsData);
        } else if (state.data) {
          renderCharts(state.data);
        }
      }, 150);
    });
  }

  function setTheme(isDark) {
    state.isDarkTheme = isDark;
    if (isDark) {
      document.body.classList.remove('light-theme');
      document.body.classList.add('dark-theme');
      el.themeIcon.textContent = '🌙';
      localStorage.setItem('myccusage_theme', 'dark');
    } else {
      document.body.classList.remove('dark-theme');
      document.body.classList.add('light-theme');
      el.themeIcon.textContent = '☀️';
      localStorage.setItem('myccusage_theme', 'light');
    }
    // 重新渲染图表以应用主题颜色
    if (state.agent === 'all' && state.allAgentsData) {
      renderCharts(state.allAgentsData);
      renderRaceChart(state.allAgentsData);
    } else if (state.data) {
      renderCharts(state.data);
    }
  }

  // 数据拉取与渲染
  async function loadData() {
    el.ledgerContainer.innerHTML = `
      <div class="loading-state">
        <div class="spinner"></div>
        <p>正在拉取并解析会话数据...</p>
      </div>
    `;

    if (state.agent === 'all') {
      // 全景模式：图表区与各 Agent 对比卡片区全部显示，展开竞赛折线图，隐藏单 Agent 会话账本区
      el.chartsSection.style.display = 'grid';
      el.allAgentsSection.style.display = 'block';
      if (el.raceChartSection) el.raceChartSection.style.display = 'block';
      if (el.tableSection) el.tableSection.style.display = 'none';
      if (el.modeSelector) el.modeSelector.style.display = 'none';
      try {
        const res = await fetch('/api/all');
        const json = await res.json();
        state.allAgentsData = json;
        state.data = json;
        renderAllAgentsOverview(json);
      } catch (err) {
        el.ledgerContainer.innerHTML = `<div class="empty-state">❌ 拉取全景数据失败: ${err.message}</div>`;
      }
      return;
    }

    if (el.modeSelector) el.modeSelector.style.display = 'flex';
    el.chartsSection.style.display = 'grid';
    el.allAgentsSection.style.display = 'none';
    if (el.raceChartSection) el.raceChartSection.style.display = 'none';
    if (el.tableSection) el.tableSection.style.display = 'block';

    try {
      const url = `/api/data?agent=${state.agent}&mode=${state.mode}&sort=${state.sort}`;
      const res = await fetch(url);
      const json = await res.json();

      if (json.error) {
        throw new Error(json.error);
      }

      state.data = json;
      renderDashboard(json);
    } catch (err) {
      el.ledgerContainer.innerHTML = `
        <div class="empty-state">
          <p>⚠️ 无法加载数据: ${err.message}</p>
          <p style="margin-top: 8px; font-size: 0.8rem; color: var(--text-muted);">
            提示：请确认本机已执行过该 Agent，或尝试切换到其他 Agent。
          </p>
        </div>
      `;
    }
  }

  async function refreshData() {
    const originalText = el.btnRefresh.innerHTML;
    el.btnRefresh.disabled = true;
    el.btnRefresh.innerHTML = `<span class="icon">⏳</span> 刷新中...`;

    try {
      const url = `/api/refresh?agent=${state.agent}`;
      const res = await fetch(url, { method: 'POST' });
      const json = await res.json();

      if (json.error) throw new Error(json.error);

      showToast(`已成功同步最新切片数据！`);
      await loadData();
    } catch (err) {
      showToast(`刷新失败: ${err.message}`);
    } finally {
      el.btnRefresh.disabled = false;
      el.btnRefresh.innerHTML = originalText;
    }
  }

  function renderDashboard(data) {
    renderKPIs(data);
    renderCharts(data);
    filterAndRenderLedger();
  }

  // 1. KPI 卡片渲染 (动态根据选中的模型计算费用，人民币为主，美元为辅)
  function renderKPIs(data) {
    const sum = data.summary;
    const model = getActiveModel();
    const currentCost = calcCost(model, sum.inputTokens, sum.cacheTokens, sum.outputTokens);

    el.valTotalTokens.textContent = formatTokens(sum.totalTokens);
    el.subTotalTokens.textContent = `Input: ${formatTokens(sum.inputTokens)} | Cache: ${formatTokens(sum.cacheTokens)} | Output: ${formatTokens(sum.outputTokens)}`;

    el.valTotalCost.textContent = formatKpiMainCost(model, currentCost);
    el.valTotalCostUsd.textContent = formatKpiSubCost(model, currentCost);

    const costBadge = document.querySelector('.highlight-card .kpi-badge');
    if (costBadge) costBadge.textContent = model.name;
    const costTitle = document.querySelector('.highlight-card .kpi-title');
    if (costTitle) costTitle.textContent = `${model.name} 等效费用`;

    el.valCacheHitRate.textContent = `${sum.cacheHitRate.toFixed(1)}%`;
    el.barCacheHit.style.width = `${Math.min(100, Math.max(0, sum.cacheHitRate))}%`;

    if (data.mode === 'daily') {
      el.badgeActivePeriod.textContent = '活动日';
      el.valActiveDays.textContent = `${data.activeDaysCount} 天`;
      const dailyAvg = data.activeDaysCount > 0 ? (sum.totalTokens / data.activeDaysCount) : 0;
      el.subActiveDays.textContent = `日均约 ${formatTokens(dailyAvg)}`;
      el.badgeRecordsType.textContent = '日度会话';
      el.valRecordsCount.textContent = `${data.totalRecordsCount} 笔`;
    } else {
      el.badgeActivePeriod.textContent = '项目总览';
      el.valActiveDays.textContent = `${data.totalRecordsCount} 个`;
      el.subActiveDays.textContent = `全生命周期累计`;
      el.badgeRecordsType.textContent = '任务统计';
      el.valRecordsCount.textContent = `${data.totalRecordsCount} 个项目`;
    }

    // 渲染今日消耗指标卡片 (联动动态费率)
    let today = data.today;
    if (!today && Array.isArray(data.dailyTrend)) {
      const now = new Date();
      const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
      const entry = data.dailyTrend.find(d => d.date === todayStr);
      if (entry) {
        const tInp = entry.inputTokens || 0;
        const tCa = entry.cacheTokens || 0;
        today = {
          totalTokens: entry.totalTokens || 0,
          inputTokens: tInp,
          cacheTokens: tCa,
          outputTokens: entry.outputTokens || 0,
          cacheHitRate: calcHitRateStr(tCa, tInp),
          sessionCount: entry.count || 1
        };
      }
    }
    if (today && (today.totalTokens > 0 || today.sessionCount > 0)) {
      const todayCost = calcCost(model, today.inputTokens || 0, today.cacheTokens || 0, today.outputTokens || 0);
      if (el.valTodayTokens) el.valTodayTokens.textContent = formatTokens(today.totalTokens || 0);
      if (el.valTodayCost) el.valTodayCost.innerHTML = formatInlineCost(model, todayCost);
      if (el.subTodayDetail) {
        el.subTodayDetail.textContent = `缓存命中 ${today.cacheHitRate}% · ${today.sessionCount || 1} 笔会话`;
      }
    } else {
      if (el.valTodayTokens) el.valTodayTokens.textContent = '0';
      if (el.valTodayCost) el.valTodayCost.innerHTML = formatInlineCost(model, 0);
      if (el.subTodayDetail) el.subTodayDetail.textContent = '今日暂无交互记录';
    }

    // 计算并渲染近 7 天与近 14 天滚动数据
    renderRollingKPIs(data, model);
  }

  // 提取并聚合过去 N 天（包含今天，自然日倒推）的消耗与计价
  function computeRollingStats(data, days) {
    // 获取基准日期 (以当地今天 00:00:00 为基准，若无记录则用系统当前时间)
    const now = new Date();
    const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    
    // 计算截止起始日期字符串 YYYY-MM-DD
    const cutoffDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (days - 1));
    const cutoffStr = `${cutoffDate.getFullYear()}-${String(cutoffDate.getMonth() + 1).padStart(2, '0')}-${String(cutoffDate.getDate()).padStart(2, '0')}`;

    let inputSum = 0;
    let cacheSum = 0;
    let outputSum = 0;
    let totalSum = 0;

    if (data.mode === 'daily' && Array.isArray(data.dailyTrend)) {
      // 在 daily 模式下直接读取精确到日的 dailyTrend
      data.dailyTrend.forEach(d => {
        if (d.date && d.date >= cutoffStr && d.date <= todayStr) {
          inputSum += (d.inputTokens || 0);
          cacheSum += (d.cacheTokens || 0);
          outputSum += (d.outputTokens || 0);
          totalSum += (d.totalTokens || 0);
        }
      });
    } else if (Array.isArray(data.weeks)) {
      // 在 session 分周模式下，遍历各个自然日
      data.weeks.forEach(w => {
        if (Array.isArray(w.days)) {
          w.days.forEach(d => {
            if (d.date && d.date >= cutoffStr && d.date <= todayStr) {
              inputSum += (d.inputTokens || 0);
              cacheSum += (d.cacheTokens || 0);
              outputSum += (d.outputTokens || 0);
              totalSum += (d.totalTokens || 0);
            }
          });
        }
      });
    } else if (Array.isArray(data.flatRecords)) {
      // 备选 fallback: 遍历扁平记录按 lastActivity 过滤
      data.flatRecords.forEach(r => {
        const act = r.lastActivity || '';
        const dStr = act.slice(0, 10);
        if (dStr && dStr >= cutoffStr && dStr <= todayStr) {
          inputSum += (r.inputTokens || 0);
          cacheSum += (r.cacheTokens || 0);
          outputSum += (r.outputTokens || 0);
          totalSum += (r.totalTokens || 0);
        }
      });
    }

    return {
      days,
      inputTokens: inputSum,
      cacheTokens: cacheSum,
      outputTokens: outputSum,
      totalTokens: totalSum
    };
  }

  function renderRollingKPIs(data, model) {
    const stats7 = computeRollingStats(data, 7);
    const cost7 = calcCost(model, stats7.inputTokens, stats7.cacheTokens, stats7.outputTokens);
    const avgTokens7 = Math.round(stats7.totalTokens / 7);
    const avgCost7 = cost7 / 7;

    if (el.val7DaysTokens) el.val7DaysTokens.textContent = formatTokens(stats7.totalTokens);
    if (el.val7DaysCost) el.val7DaysCost.innerHTML = formatInlineCost(model, cost7);
    if (el.val7DaysAvgTokens) el.val7DaysAvgTokens.textContent = formatTokens(avgTokens7);
    if (el.val7DaysAvgCost) el.val7DaysAvgCost.innerHTML = formatInlineCost(model, avgCost7);

    const stats14 = computeRollingStats(data, 14);
    const cost14 = calcCost(model, stats14.inputTokens, stats14.cacheTokens, stats14.outputTokens);
    const avgTokens14 = Math.round(stats14.totalTokens / 14);
    const avgCost14 = cost14 / 14;

    if (el.val14DaysTokens) el.val14DaysTokens.textContent = formatTokens(stats14.totalTokens);
    if (el.val14DaysCost) el.val14DaysCost.innerHTML = formatInlineCost(model, cost14);
    if (el.val14DaysAvgTokens) el.val14DaysAvgTokens.textContent = formatTokens(avgTokens14);
    if (el.val14DaysAvgCost) el.val14DaysAvgCost.innerHTML = formatInlineCost(model, avgCost14);
  }

  // 左右两侧固定 Y 轴刻度动态对齐绘制
  function renderTrendYAxisOverlays(chartInstance) {
    const chart = chartInstance || state.trendChartInstance;
    if (!chart || !chart.scales) return;
    const yScale = chart.scales.y;
    const yCostScale = chart.scales.yCost;
    if (!yScale || !yCostScale) return;

    if (el.trendYAxisLeft && Array.isArray(yScale.ticks)) {
      let leftHtml = '';
      yScale.ticks.forEach(t => {
        const px = yScale.getPixelForValue(t.value);
        if (typeof px === 'number' && !isNaN(px)) {
          leftHtml += `<span class="y-axis-label y-axis-label-left" style="top:${px}px;">${formatTokens(t.value)}</span>`;
        }
      });
      el.trendYAxisLeft.innerHTML = leftHtml;
    }

    if (el.trendYAxisRight && Array.isArray(yCostScale.ticks)) {
      let rightHtml = '';
      yCostScale.ticks.forEach(t => {
        const px = yCostScale.getPixelForValue(t.value);
        if (typeof px === 'number' && !isNaN(px)) {
          rightHtml += `<span class="y-axis-label y-axis-label-right" style="top:${px}px;">¥${t.value}</span>`;
        }
      });
      el.trendYAxisRight.innerHTML = rightHtml;
    }
  }

  // 2. 图表渲染 (动态联动选中模型费率，金额轴默认使用人民币 CNY ¥)
  function renderCharts(data) {
    if (typeof Chart === 'undefined') {
      document.getElementById('trendChartFallback').style.display = 'block';
      document.getElementById('donutChartFallback').style.display = 'block';
      renderDonutLegendStats(data.summary);
      return;
    }

    const isDark = state.isDarkTheme;
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
    const textColor = isDark ? '#9ca3af' : '#475569';

    if (state.trendChartInstance) {
      state.trendChartInstance.destroy();
      state.trendChartInstance = null;
    }

    const model = getActiveModel();
    const trend = data.dailyTrend || [];
    const totalDays = trend.length;
    const labels = trend.map(t => t.date.slice(5) + `(${t.weekday})`);
    const outputTokens = trend.map(t => t.outputTokens);
    const inputTokens = trend.map(t => t.inputTokens);
    const cacheTokens = trend.map(t => t.cacheTokens);
    const costData = trend.map(t => {
      const c = calcCost(model, t.inputTokens, t.cacheTokens, t.outputTokens);
      return Number(toCnyCost(model, c).toFixed(2));
    });

    el.trendChartTitle.textContent = state.agent === 'all'
      ? `全平台 Agent 每日 Token 消耗趋势与等效费用走向 (CNY ¥)`
      : (data.mode === 'daily' 
          ? `${data.displayName} 每日 Token 消耗趋势与等效费用走向 (CNY ¥)`
          : `${data.displayName} 会话活跃分布与费用统计 (CNY ¥)`);

    // 默认展示近 30 天：根据天数动态计算可滑动画布宽度 (仅小组件内部延展)
    const viewportWidth = (el.trendScrollViewport && el.trendScrollViewport.clientWidth > 0)
      ? el.trendScrollViewport.clientWidth
      : 600;

    if (totalDays > 30) {
      // 保持一屏舒适呈现约 30 天的柱状间距，超出天数横向延展
      const dayWidth = Math.max(28, Math.floor(viewportWidth / 30));
      const totalWidth = Math.round(totalDays * dayWidth);
      if (el.trendScrollCanvasWrap) {
        el.trendScrollCanvasWrap.style.width = `${totalWidth}px`;
      }
      if (el.trendScrollBarWrap) {
        el.trendScrollBarWrap.style.display = 'flex';
      }
      if (el.trendScrollHintText) {
        el.trendScrollHintText.textContent = `📅 默认展示近 30 天 · 可向左横滑查看全部 ${totalDays} 天历史`;
      }
    } else {
      if (el.trendScrollCanvasWrap) {
        el.trendScrollCanvasWrap.style.width = '100%';
      }
      if (el.trendScrollBarWrap) {
        el.trendScrollBarWrap.style.display = 'none';
      }
    }

    // Chart.js 布局完成回调插件：自动同步固定刻度
    const syncYAxisPlugin = {
      id: 'syncYAxisOverlays',
      afterLayout: (chart) => {
        renderTrendYAxisOverlays(chart);
      }
    };

    state.trendChartInstance = new Chart(el.trendChartCanvas, {
      type: 'bar',
      plugins: [syncYAxisPlugin],
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Output',
            data: outputTokens,
            backgroundColor: '#f43f5e',
            stack: 'tokens',
            yAxisID: 'y'
          },
          {
            label: 'Input (未命中)',
            data: inputTokens,
            backgroundColor: '#f59e0b',
            stack: 'tokens',
            yAxisID: 'y'
          },
          {
            label: 'Cache (命中)',
            data: cacheTokens,
            backgroundColor: '#10b981',
            stack: 'tokens',
            yAxisID: 'y'
          },
          {
            label: `等效费用 (CNY ¥)`,
            data: costData,
            type: 'line',
            borderColor: '#818cf8',
            backgroundColor: 'rgba(129, 140, 248, 0.15)',
            borderWidth: 2.5,
            pointBackgroundColor: '#6366f1',
            pointRadius: 3,
            fill: false,
            tension: 0.25,
            yAxisID: 'yCost'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function (items) {
                if (!items.length) return '';
                const idx = items[0].dataIndex;
                const d = trend[idx];
                if (!d) return items[0].label;
                const totalTokens = (d.outputTokens || 0) + (d.inputTokens || 0) + (d.cacheTokens || 0);
                return `${d.date.slice(5)}(${d.weekday})  ${formatTokens(totalTokens)}`;
              },
              label: function (ctx) {
                if (ctx.dataset.yAxisID === 'yCost') {
                  const val = ctx.raw;
                  if (model.currency === 'USD') {
                    const usdVal = (val / USD_CNY_RATE).toFixed(2);
                    return `${ctx.dataset.label}: ¥${val} (原 $${usdVal} USD)`;
                  }
                  return `${ctx.dataset.label}: ¥${val}`;
                }
                return `${ctx.dataset.label}: ${formatTokens(ctx.raw)}`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: textColor,
              font: { size: 10 }
            }
          },
          y: {
            position: 'left',
            stacked: true,
            grid: { color: gridColor },
            border: { display: false },
            ticks: {
              display: false // 隐藏内部画布刻度，固定于左侧固定列中展示
            }
          },
          yCost: {
            position: 'right',
            grid: { display: false },
            border: { display: false },
            ticks: {
              display: false // 隐藏内部画布刻度，固定于右侧固定列中展示
            }
          }
        }
      }
    });

    // 默认滑到最近 30 天的位置 (最右侧)
    if (totalDays > 30 && el.trendScrollViewport) {
      requestAnimationFrame(() => {
        setTimeout(() => {
          if (el.trendScrollViewport) {
            const maxScroll = el.trendScrollViewport.scrollWidth - el.trendScrollViewport.clientWidth;
            el.trendScrollViewport.scrollLeft = maxScroll;
            if (el.btnSnapLatest) el.btnSnapLatest.style.display = 'none';
          }
        }, 50);
      });
    }

    // 环形图 (Token 构成分析)
    if (state.donutChartInstance) {
      state.donutChartInstance.destroy();
    }

    const sum = data.summary;
    state.donutChartInstance = new Chart(el.donutChartCanvas, {
      type: 'doughnut',
      data: {
        labels: ['Cache 命中', 'Input 未命中', 'Output (含CoT)'],
        datasets: [{
          data: [sum.cacheTokens, sum.inputTokens, sum.outputTokens],
          backgroundColor: ['#10b981', '#f59e0b', '#f43f5e'],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '72%',
        plugins: {
          legend: { display: false }
        }
      }
    });

    renderDonutLegendStats(sum);
  }

  function renderDonutLegendStats(sum) {
    const tot = Math.max(1, sum.totalTokens);
    const cachePct = ((sum.cacheTokens / tot) * 100).toFixed(1);
    const inputPct = ((sum.inputTokens / tot) * 100).toFixed(1);
    const outputPct = ((sum.outputTokens / tot) * 100).toFixed(1);
    const model = getActiveModel();
    const sym = model.currency === 'USD' ? '$' : '¥';

    el.donutStats.innerHTML = `
      <div class="donut-stat-item">
        <div class="donut-stat-header">
          <span><span class="legend-dot dot-cache"></span>Cache 命中 (${sym}${formatRate(model.cacheRate)}/M)</span>
          <span style="font-family: monospace; font-weight:600;">${cachePct}% (${formatTokens(sum.cacheTokens)})</span>
        </div>
        <div class="donut-stat-bar">
          <div class="donut-stat-fill" style="width: ${cachePct}%; background-color: var(--color-cache);"></div>
        </div>
      </div>
      <div class="donut-stat-item">
        <div class="donut-stat-header">
          <span><span class="legend-dot dot-input"></span>Input 未命中 (${sym}${formatRate(model.inputRate)}/M)</span>
          <span style="font-family: monospace; font-weight:600;">${inputPct}% (${formatTokens(sum.inputTokens)})</span>
        </div>
        <div class="donut-stat-bar">
          <div class="donut-stat-fill" style="width: ${inputPct}%; background-color: var(--color-input);"></div>
        </div>
      </div>
      <div class="donut-stat-item">
        <div class="donut-stat-header">
          <span><span class="legend-dot dot-output"></span>Output 思考+输出 (${sym}${formatRate(model.outputRate)}/M)</span>
          <span style="font-family: monospace; font-weight:600;">${outputPct}% (${formatTokens(sum.outputTokens)})</span>
        </div>
        <div class="donut-stat-bar">
          <div class="donut-stat-fill" style="width: ${outputPct}%; background-color: var(--color-output);"></div>
        </div>
      </div>
    `;
  }

  // ==========================================================================
  // 多 Agent 每日用量竞赛折线图 (Multi-Agent Competition Line Chart)
  // ==========================================================================

  const AGENT_COLORS = {
    agy: { stroke: '#4285f4', bg: 'rgba(66, 133, 244, 0.15)', name: 'Google Antigravity' },
    claude: { stroke: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)', name: 'Claude Code' },
    hermes: { stroke: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', name: 'Hermes Agent' },
    codex: { stroke: '#06b6d4', bg: 'rgba(6, 182, 212, 0.15)', name: 'OpenAI Codex' },
    grok: { stroke: '#ec4899', bg: 'rgba(236, 72, 153, 0.15)', name: 'Grok' },
    pi: { stroke: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.15)', name: 'Pi Agent' },
    opencode: { stroke: '#6366f1', bg: 'rgba(99, 102, 241, 0.15)', name: 'OpenCode' },
    workbuddy: { stroke: '#f43f5e', bg: 'rgba(244, 63, 94, 0.15)', name: 'WorkBuddy' },
  };

  function renderRaceYAxisOverlays(chartInstance) {
    const chart = chartInstance || state.raceChartInstance;
    if (!chart || !chart.scales) return;
    const yScale = chart.scales.y;
    if (!yScale) return;

    if (el.raceYAxisLeft && Array.isArray(yScale.ticks)) {
      let leftHtml = '';
      yScale.ticks.forEach(t => {
        const px = yScale.getPixelForValue(t.value);
        if (typeof px === 'number' && !isNaN(px)) {
          leftHtml += `<span class="y-axis-label y-axis-label-left" style="top:${px}px;">${formatTokens(t.value)}</span>`;
        }
      });
      el.raceYAxisLeft.innerHTML = leftHtml;
    }
  }

  function renderRaceLegend(allData) {
    if (!el.raceLegendBar) return;
    const agents = allData.agents || [];
    let html = '';
    agents.forEach(a => {
      const col = AGENT_COLORS[a.id] || { stroke: '#94a3b8' };
      const isDimmed = state.highlightedAgent && state.highlightedAgent !== a.id;
      const isHighlighted = state.highlightedAgent === a.id;
      const isHidden = state.hiddenAgents && state.hiddenAgents.has(a.id);

      let classes = 'race-legend-pill';
      if (isHighlighted) classes += ' highlighted';
      if (isDimmed) classes += ' dimmed';
      if (isHidden) classes += ' hidden';

      html += `
        <div class="${classes}" data-agent="${a.id}" title="点击聚焦高亮 ${a.name} 折线，再次点击取消">
          <span class="race-legend-dot" style="background-color: ${col.stroke};"></span>
          <span>${a.name}</span>
          <span class="race-legend-val">${formatTokens(a.totalTokens)}</span>
        </div>
      `;
    });

    if (state.highlightedAgent || (state.hiddenAgents && state.hiddenAgents.size > 0)) {
      html += `
        <div class="race-legend-pill btn-reset-race-legend" style="border-style: dashed; color: var(--accent-blue);" title="还原所有折线">
          <span>↺ 还原全部</span>
        </div>
      `;
    }

    el.raceLegendBar.innerHTML = html;

    el.raceLegendBar.querySelectorAll('.race-legend-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        if (pill.classList.contains('btn-reset-race-legend')) {
          state.highlightedAgent = null;
          state.hiddenAgents.clear();
          renderRaceChart(allData);
          return;
        }
        const aid = pill.getAttribute('data-agent');
        if (state.highlightedAgent === aid) {
          state.highlightedAgent = null;
        } else {
          state.highlightedAgent = aid;
        }
        renderRaceChart(allData);
      });
    });
  }

  function renderRaceChart(allData) {
    if (!allData || !allData.dailyTrend || typeof Chart === 'undefined') return;

    renderRaceLegend(allData);

    const isDark = state.isDarkTheme;
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
    const textColor = isDark ? '#9ca3af' : '#475569';

    if (state.raceChartInstance) {
      state.raceChartInstance.destroy();
      state.raceChartInstance = null;
    }

    let trend = allData.dailyTrend || [];
    if (state.raceRange === '14') {
      trend = trend.slice(-14);
    } else if (state.raceRange === '30') {
      trend = trend.slice(-30);
    }
    const totalDays = trend.length;
    const labels = trend.map(t => t.date.slice(5) + `(${t.weekday})`);

    const viewportWidth = (el.raceScrollViewport && el.raceScrollViewport.clientWidth > 0)
      ? el.raceScrollViewport.clientWidth
      : 600;

    if (totalDays > 30) {
      const dayWidth = Math.max(34, Math.floor(viewportWidth / 30));
      const totalWidth = Math.round(totalDays * dayWidth);
      if (el.raceScrollCanvasWrap) {
        el.raceScrollCanvasWrap.style.width = `${totalWidth}px`;
      }
    } else {
      if (el.raceScrollCanvasWrap) {
        el.raceScrollCanvasWrap.style.width = '100%';
      }
    }

    const agents = allData.agents || [];
    const datasets = [];

    agents.forEach(a => {
      if (state.hiddenAgents && state.hiddenAgents.has(a.id)) return;
      const col = AGENT_COLORS[a.id] || { stroke: '#94a3b8', bg: 'rgba(148, 163, 184, 0.15)' };
      const isHighlighted = state.highlightedAgent === a.id;
      const isDimmed = state.highlightedAgent && state.highlightedAgent !== a.id;

      const lineData = trend.map(t => (t.agentTokens && t.agentTokens[a.id]) || 0);

      datasets.push({
        label: a.name,
        agentId: a.id,
        data: lineData,
        borderColor: isDimmed ? 'rgba(156, 163, 175, 0.22)' : col.stroke,
        backgroundColor: col.bg,
        borderWidth: isHighlighted ? 3.5 : (isDimmed ? 1.0 : 2.2),
        pointBackgroundColor: isDimmed ? 'rgba(156, 163, 175, 0.22)' : col.stroke,
        pointBorderColor: isDark ? '#1e293b' : '#ffffff',
        pointBorderWidth: 1.5,
        pointRadius: isHighlighted ? 4.5 : (isDimmed ? 1.0 : 3),
        pointHoverRadius: 6,
        tension: 0.25,
        fill: false,
        order: isHighlighted ? 1 : 10
      });
    });

    const syncRaceYAxisPlugin = {
      id: 'syncRaceYAxisOverlays',
      afterLayout: (chart) => {
        renderRaceYAxisOverlays(chart);
      }
    };

    state.raceChartInstance = new Chart(el.raceChartCanvas, {
      type: 'line',
      plugins: [syncRaceYAxisPlugin],
      data: {
        labels: labels,
        datasets: datasets
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: isDark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.95)',
            titleColor: isDark ? '#f8fafc' : '#0f172a',
            bodyColor: isDark ? '#cbd5e1' : '#334155',
            borderColor: isDark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.1)',
            borderWidth: 1,
            padding: 12,
            boxPadding: 6,
            usePointStyle: true,
            itemSort: (a, b) => (b.raw || 0) - (a.raw || 0),
            callbacks: {
              title: function (items) {
                if (!items.length) return '';
                const idx = items[0].dataIndex;
                const d = trend[idx];
                return d ? `📅 ${d.date} (${d.weekday})` : items[0].label;
              },
              label: function (ctx) {
                const val = ctx.raw || 0;
                if (val <= 0 && state.highlightedAgent !== ctx.dataset.agentId) {
                  return null;
                }
                return ` ${ctx.dataset.label}: ${formatTokens(val)}`;
              },
              footer: function (items) {
                const activeItems = items.filter(it => (it.raw || 0) > 0);
                const total = activeItems.reduce((acc, c) => acc + (c.raw || 0), 0);
                return total > 0 ? `当日全平台总计: ${formatTokens(total)}` : '';
              }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: textColor,
              font: { size: 10 }
            }
          },
          y: {
            position: 'left',
            grid: { color: gridColor },
            ticks: {
              display: false,
              font: { size: 10 }
            }
          }
        }
      }
    });

    if (totalDays > 30 && el.raceScrollViewport) {
      setTimeout(() => {
        if (el.raceScrollViewport) {
          const maxScroll = el.raceScrollViewport.scrollWidth - el.raceScrollViewport.clientWidth;
          el.raceScrollViewport.scrollLeft = maxScroll;
        }
      }, 50);
    }
  }

  // 3. 全景对比视图渲染
  function renderAllAgentsOverview(allData) {
    const gs = allData.grandSummary;
    const model = getActiveModel();
    const grandCost = (gs.inputTokens !== undefined || gs.cacheTokens !== undefined || gs.outputTokens !== undefined)
      ? calcCost(model, gs.inputTokens, gs.cacheTokens, gs.outputTokens)
      : (gs.costCny || 0);

    // 1) 核心 KPI 全周期卡片
    el.valTotalTokens.textContent = formatTokens(gs.totalTokens);
    el.subTotalTokens.textContent = `全平台 ${allData.agents.length} 大 Agent 累计消耗`;
    el.valTotalCost.textContent = formatKpiMainCost(model, grandCost);
    el.valTotalCostUsd.textContent = formatKpiSubCost(model, grandCost);

    const costBadge = document.querySelector('.highlight-card .kpi-badge');
    if (costBadge) costBadge.textContent = model.name;
    const costTitle = document.querySelector('.highlight-card .kpi-title');
    if (costTitle) costTitle.textContent = `${model.name} 等效费用`;

    const hitRate = (gs.cacheHitRate !== undefined && gs.cacheHitRate !== null)
      ? gs.cacheHitRate
      : (gs.inputTokens + gs.cacheTokens > 0 ? ((gs.cacheTokens / (gs.inputTokens + gs.cacheTokens)) * 100).toFixed(1) : '0.0');
    el.valCacheHitRate.textContent = `${hitRate}%`;
    el.barCacheHit.style.width = `${Math.min(100, Math.max(0, parseFloat(hitRate) || 0))}%`;

    el.badgeActivePeriod.textContent = '活动日';
    const activeDays = allData.activeDaysCount || (allData.dailyTrend ? allData.dailyTrend.length : 1);
    el.valActiveDays.textContent = `${activeDays} 天`;
    const dailyAvg = activeDays > 0 ? Math.round(gs.totalTokens / activeDays) : 0;
    el.subActiveDays.textContent = `日均约 ${formatTokens(dailyAvg)}`;

    el.badgeRecordsType.textContent = '总会话数';
    el.valRecordsCount.textContent = `${gs.totalSessions} 笔`;
    if (el.subRecordsDetail) el.subRecordsDetail.textContent = `共 ${allData.agents.length} 款 Agent 矩阵`;

    // 2) 今日消耗指标卡片 (动态联动所选模型费率)
    const today = allData.today || {};
    const todayTokens = today.totalTokens || 0;
    const todayCost = calcCost(model, today.inputTokens || 0, today.cacheTokens || 0, today.outputTokens || 0);
    if (el.valTodayTokens) el.valTodayTokens.textContent = formatTokens(todayTokens);
    if (el.valTodayCost) el.valTodayCost.innerHTML = formatInlineCost(model, todayCost);
    if (el.subTodayDetail) {
      el.subTodayDetail.textContent = todayTokens > 0
        ? `缓存命中 ${today.cacheHitRate}% · ${today.activeAgentsCount || 0} 个活跃 Agent`
        : `今日暂无交互记录`;
    }

    // 3) 过去 7 天 / 14 天滚动消耗指标卡片 (基于聚合的 dailyTrend 准确计算)
    renderRollingKPIs(allData, model);

    // 4) 柱状统计图表与饼图 (全景模式下直观展现全平台每日走向)
    renderCharts(allData);

    // 5) 渲染各 Agent 横向对比卡片
    let html = '';
    let agentsList = [...allData.agents];
    if (state.sort === 'tokens') {
      agentsList.sort((a, b) => (b.totalTokens || 0) - (a.totalTokens || 0));
    }
    agentsList.forEach(a => {
      const aCost = (a.inputTokens !== undefined || a.cacheTokens !== undefined || a.outputTokens !== undefined)
        ? calcCost(model, a.inputTokens, a.cacheTokens, a.outputTokens)
        : (a.costCny || 0);
      html += `
        <div class="agent-stat-card" data-agent="${a.id}">
          <div class="agent-stat-name">
            <span>${a.name}</span>
            <span class="badge ${a.totalTokens > 0 ? 'badge-blue' : 'badge-subtle'}">
              ${a.recordsCount} 笔会话
            </span>
          </div>
          <div class="agent-stat-values">
            <span class="agent-token-num">${formatTokens(a.totalTokens)}</span>
            <span class="agent-cost-num">${formatInlineCost(model, aCost)}</span>
          </div>
          <div style="margin-top: 8px; font-size: 0.75rem; color: var(--text-muted);">
            Prompt 缓存命中率: <strong style="color: var(--color-cache);">${a.cacheHitRate}%</strong>
          </div>
        </div>
      `;
    });
    el.agentsOverviewGrid.innerHTML = html;

    // 点击直接切换
    el.agentsOverviewGrid.querySelectorAll('.agent-stat-card').forEach(card => {
      card.addEventListener('click', () => {
        const ag = card.getAttribute('data-agent');
        const targetBtn = document.querySelector(`.segment-btn[data-agent="${ag}"]`);
        if (targetBtn) {
          targetBtn.click();
        }
      });
    });

    el.ledgerContainer.innerHTML = `
      <div class="empty-state">
        <p>💡 点击上方任意 Agent 卡片可深入查看其精准每日账本与会话明细。</p>
      </div>
    `;
    el.recordCounter.textContent = `共 ${allData.agents.length} 个 Agent 矩阵`;

    // 6) 渲染多 Agent 每日用量竞赛折线图
    renderRaceChart(allData);
  }

  // 4. 账本/项目列表渲染与过滤
  function filterAndRenderLedger() {
    if (!state.data) return;
    const data = state.data;
    const q = state.searchQuery;

    // 检查如果是按照 Token 排行（扁平列表）或 session 模式且指定了扁平结构
    if (data.sortByTokens || (data.flatRecords && !data.weeks)) {
      renderFlatTable(data.flatRecords, q);
      return;
    }

    if (state.sort === 'tokens') {
      renderFlatTable(data.flatRecords, q);
      return;
    }

    // 时间排序 (树状周/日账本，默认 Web 端倒序)
    renderGroupedAccordion(data.weeks, q);
  }

  function renderFlatTable(records, query) {
    let filtered = query
      ? records.filter(r => (r.title && r.title.toLowerCase().includes(query)) || (r.sessionId && r.sessionId.toLowerCase().includes(query)) || (r.date && r.date.includes(query)))
      : [...records];

    if (state.sort === 'tokens') {
      filtered.sort((a, b) => (b.totalTokens || 0) - (a.totalTokens || 0));
      el.recordCounter.textContent = `共 ${filtered.length} 条记录 (按 Token 消耗降序)`;
    } else {
      // 时间排序：Web 默认倒序 (最新在最顶上)
      if (state.timeSortOrder === 'desc') {
        filtered.sort((a, b) => (b.isoTime || b.lastActivity || b.time || '').localeCompare(a.isoTime || a.lastActivity || a.time || ''));
        el.recordCounter.textContent = `共 ${filtered.length} 条记录 (按时间倒序 - 最新在顶)`;
      } else {
        filtered.sort((a, b) => (a.isoTime || a.lastActivity || a.time || '').localeCompare(b.isoTime || b.lastActivity || b.time || ''));
        el.recordCounter.textContent = `共 ${filtered.length} 条记录 (按时间正序 - 最新在底)`;
      }
    }

    if (filtered.length === 0) {
      el.ledgerContainer.innerHTML = `<div class="empty-state">🔍 未找到匹配的记录</div>`;
      return;
    }

    const model = getActiveModel();
    let rowsHtml = '';
    filtered.forEach((r, idx) => {
      const rCost = calcCost(model, r.inputTokens, r.cacheTokens, r.outputTokens);
      rowsHtml += `
        <tr>
          <td class="col-rank">${idx + 1}</td>
          <td class="col-time">${r.time || r.date || '--'}</td>
          <td class="col-tokens">${formatTokens(r.totalTokens)}</td>
          <td class="col-input">${formatTokens(r.inputTokens)}</td>
          <td class="col-output">${formatTokens(r.outputTokens)}</td>
          <td class="col-cache">${formatTokens(r.cacheTokens)}</td>
          <td class="col-hitrate">${calcHitRateStr(r.cacheTokens, r.inputTokens)}</td>
          <td class="col-cost">${formatLedgerCost(model, rCost)}</td>
          <td class="col-title">
            <div class="title-cell">
              <span class="title-text" title="${escapeHtml(r.title)}">${escapeHtml(r.title)}</span>${r.remoteDevice ? ` <span class="remote-device-tag">💻 ${escapeHtml(r.remoteDevice)}</span>` : ''}
              ${r.sessionId ? `<button class="copy-id-btn" data-id="${r.sessionId}" title="复制 Session ID">ID</button>` : ''}
            </div>
          </td>
        </tr>
      `;
    });

    el.ledgerContainer.innerHTML = `
      <div class="session-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th class="col-rank">序号</th>
              <th class="col-time">最近访问</th>
              <th class="col-tokens">总Token</th>
              <th class="col-input">Input</th>
              <th class="col-output">Output</th>
              <th class="col-cache">Cache</th>
              <th class="col-hitrate">Hitrate</th>
              <th class="col-cost">等效费用 (CNY ¥)</th>
              <th class="col-title">会话标题</th>
            </tr>
          </thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>
    `;

    bindCopyButtons();
  }

  function renderGroupedAccordion(weeks, query) {
    if (!weeks || weeks.length === 0) {
      el.ledgerContainer.innerHTML = `<div class="empty-state">暂无活动会话记录</div>`;
      el.recordCounter.textContent = `0 条记录`;
      return;
    }

    let totalMatched = 0;
    let weeksHtml = '';
    const model = getActiveModel();
    const weeksToRender = state.timeSortOrder === 'desc' ? [...weeks].reverse() : [...weeks];

    weeksToRender.forEach(w => {
      let daysHtml = '';
      let weekHasMatch = false;

      const daysToRender = state.timeSortOrder === 'desc' ? [...w.days].reverse() : [...w.days];

      daysToRender.forEach(d => {
        const filteredRecords = query
          ? d.records.filter(r => (r.title && r.title.toLowerCase().includes(query)) || (r.sessionId && r.sessionId.toLowerCase().includes(query)) || d.date.includes(query))
          : d.records;

        if (filteredRecords.length === 0 && query) {
          return;
        }

        weekHasMatch = true;
        totalMatched += filteredRecords.length;

        // 当日会话记录：若为倒序模式，最新会话显示在当日小表最顶部
        const recordsToRender = state.timeSortOrder === 'desc' ? [...filteredRecords].reverse() : [...filteredRecords];

        let tableRows = '';
        recordsToRender.forEach(r => {
          const rCost = calcCost(model, r.inputTokens, r.cacheTokens, r.outputTokens);
          tableRows += `
            <tr>
              <td class="col-rank">${r.index}</td>
              <td class="col-time">${r.time}</td>
              <td class="col-tokens">${formatTokens(r.totalTokens)}</td>
              <td class="col-input">${formatTokens(r.inputTokens)}</td>
              <td class="col-output">${formatTokens(r.outputTokens)}</td>
              <td class="col-cache">${formatTokens(r.cacheTokens)}</td>
              <td class="col-hitrate">${calcHitRateStr(r.cacheTokens, r.inputTokens)}</td>
              <td class="col-cost">${formatLedgerCost(model, rCost)}</td>
              <td class="col-title">
                <div class="title-cell">
                  <span class="title-text" title="${escapeHtml(r.title)}">${escapeHtml(r.title)}</span>${r.remoteDevice ? ` <span class="remote-device-tag">💻 ${escapeHtml(r.remoteDevice)}</span>` : ''}
                  ${r.sessionId ? `<button class="copy-id-btn" data-id="${r.sessionId}" title="复制 Session ID">ID</button>` : ''}
                </div>
              </td>
            </tr>
          `;
        });

        const dayShort = d.date.length >= 10 ? d.date.slice(5) : d.date;
        const dCost = calcCost(model, d.inputTokens, d.cacheTokens, d.outputTokens);
        daysHtml += `
          <div class="day-block">
            <div class="day-header" onclick="this.parentElement.classList.toggle('collapsed')">
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="accordion-chevron">▼</span>
                <strong>${dayShort} (${d.weekday}) 小计</strong>
                <span style="font-size:0.75rem; color:var(--text-muted);">当日 ${filteredRecords.length} 笔会话</span>
              </div>
              <div class="day-stats">
                <span>总: <strong style="color:var(--accent-blue);">${formatTokens(d.totalTokens)}</strong></span>
                <span>费用: <strong style="color:var(--accent-green);">${formatInlineCost(model, dCost)}</strong></span>
              </div>
            </div>
            <div class="day-table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th class="col-rank">序号</th>
                    <th class="col-time">访问时间</th>
                    <th class="col-tokens">总Token</th>
                    <th class="col-input">Input</th>
                    <th class="col-output">Output</th>
                    <th class="col-cache">Cache</th>
                    <th class="col-hitrate">Hitrate</th>
                    <th class="col-cost">等效费用 (CNY ¥)</th>
                    <th class="col-title">会话标题</th>
                  </tr>
                </thead>
                <tbody>${tableRows}</tbody>
              </table>
            </div>
          </div>
        `;
      });

      if (weekHasMatch) {
        const wCost = calcCost(model, w.inputTokens, w.cacheTokens, w.outputTokens);
        weeksHtml += `
          <div class="week-card">
            <div class="week-header" onclick="this.parentElement.classList.toggle('collapsed')">
              <div class="week-title-left">
                <span class="accordion-chevron">▼</span>
                <span>${w.weekKey} 小计</span>
                <span class="badge badge-subtle">${w.count} 笔会话</span>
              </div>
              <div class="week-subtotal-stats">
                <span>Token: <strong class="stat-token-badge">${formatTokens(w.totalTokens)}</strong></span>
                <span>费用: <strong class="stat-cost-badge">${formatInlineCost(model, wCost)}</strong></span>
              </div>
            </div>
            <div class="week-body">${daysHtml}</div>
          </div>
        `;
      }
    });

    el.recordCounter.textContent = `共 ${totalMatched} 笔匹配记录`;

    if (!weeksHtml) {
      el.ledgerContainer.innerHTML = `<div class="empty-state">🔍 未找到与 "${query}" 匹配的会话记录</div>`;
      return;
    }

    el.ledgerContainer.innerHTML = weeksHtml;
    bindCopyButtons();
  }

  function bindCopyButtons() {
    document.querySelectorAll('.copy-id-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const sid = btn.getAttribute('data-id');
        copyToClipboard(sid, 'Session ID');
      });
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // 启动应用
  document.addEventListener('DOMContentLoaded', init);
})();
