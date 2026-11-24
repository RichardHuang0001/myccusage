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
    modelTrendRange: '30',
    highlightedModel: null,
    modelTrendChartInstance: null,
    modelDonutRange: '14',
    modelDonutChartInstance: null,
    syncState: null,

    // 模型维度视图 (Models) 专属状态
    modelsData: null,          // /api/models 的完整返回（含 byDate，供前端按时段聚合）
    modelRange: '7d',          // today | 7d | 30d | all | custom
    modelPricingMode: 'equivalent', // equivalent(等效计价) | unit(按模型单价)
    modelShareBasis: 'tokens', // tokens | cost —— 占比条的统计基数
    modelStart: '',
    modelEnd: '',
    modelFilter: '',

    // 深度分析视图 (Insights) 专属状态 —— 仅对提供 get_insights() 的 Agent 生效
    insightsData: null,
    insightsCapable: new Map()   // agentId -> true/false，缓存 /api/insights 的能力探测结果
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
    kpiSection: document.getElementById('kpiSection'),
    allAgentsSection: document.getElementById('allAgentsSection'),
    agentsOverviewGrid: document.getElementById('agentsOverviewGrid'),
    tableSection: document.getElementById('tableSection'),
    raceChartSection: document.getElementById('raceChartSection'),
    sortGroup: document.getElementById('sortGroup'),

    // 深度分析视图 (Insights) —— 仅对有 get_insights() 能力的 Agent 开放
    tabInsights: document.getElementById('tabInsights'),
    insightsSection: document.getElementById('insightsSection'),
    insightsHeadbar: document.getElementById('insightsHeadbar'),
    insightsKpiGrid: document.getElementById('insightsKpiGrid'),
    insightsToolPanel: document.getElementById('insightsToolPanel'),
    insightsSessionPanel: document.getElementById('insightsSessionPanel'),
    insightsGapsPanel: document.getElementById('insightsGapsPanel'),

    // 模型维度视图 (Models)
    modelsSection: document.getElementById('modelsSection'),
    modelRangeSelect: document.getElementById('modelRangeSelect'),
    modelCustomRange: document.getElementById('modelCustomRange'),
    modelStartDate: document.getElementById('modelStartDate'),
    modelEndDate: document.getElementById('modelEndDate'),
    modelPricingSelect: document.getElementById('modelPricingSelect'),
    modelShareBasisSelect: document.getElementById('modelShareBasisSelect'),
    btnOpenRateManager: document.getElementById('btnOpenRateManager'),
    modelFilterInput: document.getElementById('modelFilterInput'),
    modelSummaryBar: document.getElementById('modelSummaryBar'),
    modelShareChart: document.getElementById('modelShareChart'),
    modelTableWrap: document.getElementById('modelTableWrap'),
    raceChartCanvas: document.getElementById('raceChartCanvas'),
    raceYAxisLeft: document.getElementById('raceYAxisLeft'),
    raceScrollViewport: document.getElementById('raceScrollViewport'),
    raceScrollCanvasWrap: document.getElementById('raceScrollCanvasWrap'),
    raceLegendBar: document.getElementById('raceLegendBar'),
    raceRangeSelector: document.getElementById('raceRangeSelector'),
    raceChartFallback: document.getElementById('raceChartFallback'),
    modelTrendChartSection: document.getElementById('modelTrendChartSection'),
    modelTrendTitle: document.getElementById('modelTrendTitle'),
    modelTrendRangeSelector: document.getElementById('modelTrendRangeSelector'),
    modelTrendLegendBar: document.getElementById('modelTrendLegendBar'),
    modelTrendYAxisLeft: document.getElementById('modelTrendYAxisLeft'),
    modelTrendScrollViewport: document.getElementById('modelTrendScrollViewport'),
    modelTrendScrollCanvasWrap: document.getElementById('modelTrendScrollCanvasWrap'),
    modelTrendChartCanvas: document.getElementById('modelTrendChartCanvas'),
    modelTrendChartFallback: document.getElementById('modelTrendChartFallback'),
    modelDonutRangeSelector: document.getElementById('modelDonutRangeSelector'),
    modelDonutChartCanvas: document.getElementById('modelDonutChartCanvas'),
    modelDonutFallback: document.getElementById('modelDonutFallback'),
    modelDonutStats: document.getElementById('modelDonutStats'),
    modelDonutSubtitle: document.getElementById('modelDonutSubtitle'),
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
    trendChartLegend: document.getElementById('trendChartLegend'),
    tokenDonutCard: document.getElementById('tokenDonutCard'),

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

  function formatMsDuration(ms) {
    if (!ms || ms <= 0) return '0s';
    const sec = ms / 1000;
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const min = Math.floor(sec / 60);
    const remSec = Math.round(sec % 60);
    if (min < 60) return `${min}m ${remSec}s`;
    const hr = Math.floor(min / 60);
    const remMin = min % 60;
    return `${hr}h ${remMin}m`;
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
    // 先探测当前 Agent 是否具备「深度分析」能力（决定 tab 显隐），再加载主数据
    syncInsightsTab().then(() => loadData());
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
    // 模型维度视图：费率或计价方式变更后立即重算（纯内存重算，无网络请求）
    if (state.mode === 'models') {
      if (state.modelsData) renderModelsView();
      return;
    }
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
    // 费率表可能在弹窗内被新增 / 编辑 / 删除（含智能导入），关闭时同步刷新模型维度视图，
    // 使「按模型单价」计价的最新费率立即生效（纯内存重算，无网络请求）
    if (state.mode === 'models' && state.modelsData) renderModelsView();
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
    // 模型维度视图控件（时间范围 / 计价方式 / 占比口径 / 费率表 / 过滤）
    bindModelViewEvents();

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
      // 切换 Agent 后先同步「深度分析」tab 的可用性，再加载数据
      syncInsightsTab().then(() => loadData());
    });

    // 切换视图模式 (每日账本 / 项目会话 / 模型维度)
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

      // 通用横向拖拽滑动组件 (Reusable horizontal drag-to-scroll)
      function enableDragScroll(viewport) {
        if (!viewport) return;
        let isDown = false;
        let startX = 0;
        let startLeft = 0;
        viewport.addEventListener('mousedown', (e) => {
          if (e.button !== 0) return;
          isDown = true;
          viewport.classList.add('grabbing');
          startX = e.pageX - viewport.offsetLeft;
          startLeft = viewport.scrollLeft;
        });
        window.addEventListener('mouseup', () => {
          if (isDown) {
            isDown = false;
            viewport.classList.remove('grabbing');
          }
        });
        viewport.addEventListener('mousemove', (e) => {
          if (!isDown) return;
          e.preventDefault();
          const walk = (e.pageX - viewport.offsetLeft - startX) * 1.5;
          viewport.scrollLeft = startLeft - walk;
        });
      }

      enableDragScroll(el.trendScrollViewport);
      enableDragScroll(el.raceScrollViewport);
      enableDragScroll(el.modelTrendScrollViewport);
    }

    // 通用时序范围切换绑定
    function bindRangeSelector(container, onRangeChange) {
      if (!container) return;
      container.querySelectorAll('.race-range-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          container.querySelectorAll('.race-range-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          onRangeChange(btn.getAttribute('data-range') || '30');
        });
      });
    }

    bindRangeSelector(el.raceRangeSelector, (r) => {
      state.raceRange = r;
      if (state.allAgentsData) renderRaceChart(state.allAgentsData);
    });

    bindRangeSelector(el.modelTrendRangeSelector, (r) => {
      state.modelTrendRange = r;
      if (state.allAgentsData && state.modelsData) {
        renderModelTrendChart(state.allAgentsData, state.modelsData);
      }
    });

    bindRangeSelector(el.modelDonutRangeSelector, (r) => {
      state.modelDonutRange = r;
      if (state.allAgentsData && state.modelsData) {
        renderModelDonutChart(state.allAgentsData, state.modelsData);
      }
    });

    // 窗口尺寸变化自适应重绘
    window.addEventListener('resize', () => {
      clearTimeout(window._trendResizeTimer);
      window._trendResizeTimer = setTimeout(() => {
        if (state.agent === 'all' && state.allAgentsData) {
          renderCharts(state.allAgentsData);
          renderRaceChart(state.allAgentsData);
          if (state.modelsData) {
            renderModelTrendChart(state.allAgentsData, state.modelsData);
            renderModelDonutChart(state.allAgentsData, state.modelsData);
          }
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
      if (state.modelsData) {
        renderModelTrendChart(state.allAgentsData, state.modelsData);
        renderModelDonutChart(state.allAgentsData, state.modelsData);
      }
    } else if (state.data) {
      renderCharts(state.data);
    }
  }

  // 当前 Agent 是否具备「深度分析」能力（由后端 /api/insights 的 available 决定）。
  // 仅 dsh 这类上报了丰富运行指标的 Agent 才开放该 tab，绝不为不支持的 Agent 造空壳视图。
  function hasInsights(agentId) {
    return !!agentId && state.insightsCapable.get(agentId) === true;
  }

  // 视图区块显隐的统一调度（集中一处，避免 style.display 赋值散落各处而在新增视图时漏改）
  //
  // 模型维度视图与深度分析视图均采用**完全独立的布局**：不复用 Token 统计的
  // KPI 卡片与趋势/环形图，因为它们各自的口径与账本口径（按日/按会话的 Token
  // 与等效费用）无关，混排只会带来误导性的冗余文本。
  // 参数 mode：'daily' | 'session' | 'models' | 'insights'
  function applyViewLayout(mode) {
    // 视图切换 tab 在所有模式下常显（含全景对比），使模式入口保持一致
    if (el.modeSelector) el.modeSelector.style.display = 'flex';

    const isModels = mode === 'models';
    const isInsights = mode === 'insights';

    if (el.modelsSection) el.modelsSection.style.display = isModels ? 'block' : 'none';
    if (el.insightsSection) el.insightsSection.style.display = isInsights ? 'block' : 'none';
    // 「排序方式」仅对账本视图有意义；模型/深度分析自带排序口径，故在此隐藏以免误导
    if (el.sortGroup) el.sortGroup.style.display = (isModels || isInsights) ? 'none' : 'flex';

    if (isModels || isInsights) {
      if (el.kpiSection) el.kpiSection.style.display = 'none';
      el.chartsSection.style.display = 'none';
      el.allAgentsSection.style.display = 'none';
      if (el.raceChartSection) el.raceChartSection.style.display = 'none';
      if (el.modelTrendChartSection) el.modelTrendChartSection.style.display = 'none';
      if (el.tableSection) el.tableSection.style.display = 'none';
      return;
    }

    if (el.kpiSection) el.kpiSection.style.display = 'grid';
    el.chartsSection.style.display = 'grid';
    // 全景对比：移除右侧 Token 构成环形卡，趋势图独占整行（单 Agent 视图保持原布局）
    const isAllView = state.agent === 'all';
    if (el.tokenDonutCard) el.tokenDonutCard.style.display = isAllView ? 'none' : '';
    el.chartsSection.classList.toggle('chart-grid-full', isAllView);
    if (state.agent === 'all') {
      // 全景对比：展示各 Agent 对比卡片与竞赛折线图及全模型走势图，隐藏单 Agent 账本区
      el.allAgentsSection.style.display = 'block';
      if (el.raceChartSection) el.raceChartSection.style.display = 'block';
      if (el.modelTrendChartSection) el.modelTrendChartSection.style.display = 'block';
      if (el.tableSection) el.tableSection.style.display = 'none';
    } else {
      el.allAgentsSection.style.display = 'none';
      if (el.raceChartSection) el.raceChartSection.style.display = 'none';
      if (el.modelTrendChartSection) el.modelTrendChartSection.style.display = 'none';
      if (el.tableSection) el.tableSection.style.display = 'block';
    }
  }

  // 数据拉取与渲染
  async function loadData() {
    // 深度分析视图：仅当该 Agent 具备 insights 能力时可用，否则自动回退到每日账本
    if (state.mode === 'insights' && !hasInsights(state.agent)) {
      state.mode = 'daily';
      document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-mode') === 'daily');
      });
    }

    // 模型维度视图：任意 Agent 选择下都是同一套独立布局与独立数据源（/api/models）
    if (state.mode === 'models') {
      applyViewLayout('models');
      await loadAndRenderModels();
      return;
    }

    // 深度分析视图：独立布局与独立数据源（/api/insights）
    if (state.mode === 'insights') {
      applyViewLayout('insights');
      await loadAndRenderInsights();
      return;
    }

    applyViewLayout('daily');

    el.ledgerContainer.innerHTML = `
      <div class="loading-state">
        <div class="spinner"></div>
        <p>正在拉取并解析会话数据...</p>
      </div>
    `;

    if (state.agent === 'all') {
      try {
        const [allRes, modelsRes] = await Promise.all([
          fetch('/api/all'),
          fetch('/api/models?agent=all')
        ]);
        const json = await allRes.json();
        const modelsJson = await modelsRes.json();
        state.allAgentsData = json;
        state.modelsData = modelsJson;
        state.data = json;
        renderAllAgentsOverview(json);
      } catch (err) {
        el.ledgerContainer.innerHTML = `<div class="empty-state">❌ 拉取全景数据失败: ${err.message}</div>`;
      }
      return;
    }

    try {
      const url = `/api/data?agent=${state.agent}&mode=${state.mode}&sort=${state.sort}`;
      const res = await fetch(url);
      const json = await res.json();

      if (json.error) {
        throw new Error(json.error);
      }

      state.data = json;
      renderDashboard(json);

      if (state.mode === 'models') {
        await loadAndRenderModels();
      }
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
    if ((data.agent === 'workbuddy' || (sum.credit && sum.credit > 0)) && sum.credit > 0) {
      const cr = sum.credit;
      const ratio = currentCost > 0 ? (currentCost / cr).toFixed(4) : '0';
      el.valTotalCostUsd.innerHTML = `<span style="color:var(--accent-pink,#f43f5e);font-weight:600;">${cr.toFixed(2)} 官方积分</span> · 1积≈¥${ratio}`;
    } else {
      el.valTotalCostUsd.textContent = formatKpiSubCost(model, currentCost);
    }

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

  // 左右两侧固定 Y 轴刻度动态对齐绘制（全景视图无费用轴时仅绘制左侧）
  function renderTrendYAxisOverlays(chartInstance) {
    const chart = chartInstance || state.trendChartInstance;
    if (!chart || !chart.scales) return;
    const yScale = chart.scales.y;
    const yCostScale = chart.scales.yCost;
    if (!yScale) return;

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

    if (el.trendYAxisRight && yCostScale && Array.isArray(yCostScale.ticks)) {
      let rightHtml = '';
      yCostScale.ticks.forEach(t => {
        const px = yCostScale.getPixelForValue(t.value);
        if (typeof px === 'number' && !isNaN(px)) {
          rightHtml += `<span class="y-axis-label y-axis-label-right" style="top:${px}px;">¥${t.value}</span>`;
        }
      });
      el.trendYAxisRight.innerHTML = rightHtml;
    } else if (el.trendYAxisRight) {
      el.trendYAxisRight.innerHTML = '';
    }
  }

  // 全景视图趋势图例的出厂静态 HTML（首次渲染时缓存，切回单 Agent 视图时原样恢复）
  let trendLegendStaticHtml = null;

  // 全景视图：把每日柱状图按「实际调用的模型」拆分为堆叠色段。
  // 复用 /api/models 的 byDate（loadData 已并行拉取，零新增网络请求）与
  // aggregateModelsInRange / MODEL_SHARE_PALETTE 既有组件，纯内存 O(N) 聚合。
  function buildModelStackSeries(trend) {
    const byDate = (state.modelsData && state.modelsData.byDate) || null;
    if (!byDate || !trend.length) return null;

    const aggregated = aggregateModelsInRange(trend[0].date, trend[trend.length - 1].date, byDate);
    const mainModels = aggregated.slice(0, MODEL_SHARE_TOP_N);
    const otherModels = aggregated.slice(MODEL_SHARE_TOP_N);
    const otherNames = new Set(otherModels.map(m => m.model));

    const displayModels = mainModels.map((m, idx) => ({
      id: m.model,
      name: m.model === 'unknown' ? 'unknown (异机/未指定)' : m.model,
      color: MODEL_SHARE_PALETTE[idx % MODEL_SHARE_PALETTE.length],
      totalTokens: m.totalTokens
    }));
    const otherTokens = otherModels.reduce((acc, m) => acc + m.totalTokens, 0);
    if (otherTokens > 0) {
      displayModels.push({
        id: '__others__',
        name: `其他 (${otherModels.length} 款模型)`,
        color: MODEL_SHARE_REST_COLOR,
        totalTokens: otherTokens
      });
    }

    // 单次遍历建立 日期 -> {模型: tokens} 索引，避免每根柱子 × 每个模型重复 find
    const perDate = new Map();
    trend.forEach(t => {
      const list = byDate[t.date] || [];
      const bucket = {};
      let others = 0;
      for (let i = 0; i < list.length; i++) {
        const it = list[i];
        const mid = it.model || 'unknown';
        if (otherNames.has(mid)) {
          others += it.totalTokens || 0;
        } else {
          bucket[mid] = (bucket[mid] || 0) + (it.totalTokens || 0);
        }
      }
      if (others > 0) bucket.__others__ = others;
      perDate.set(t.date, bucket);
    });

    const datasets = displayModels.map(m => ({
      label: m.name,
      data: trend.map(t => (perDate.get(t.date) || {})[m.id] || 0),
      backgroundColor: m.color,
      stack: 'tokens',
      yAxisID: 'y',
      borderWidth: 0,
      maxBarThickness: 48
    }));
    return { datasets, displayModels };
  }

  // 2. 图表渲染 (动态联动选中模型费率，金额轴默认使用人民币 CNY ¥)
  //    全景对比视图改为「按模型堆叠」口径：仅柱状图 + 柱顶当日总量标签，无费用折线。
  function renderCharts(data) {
    const isAll = state.agent === 'all';
    if (typeof Chart === 'undefined') {
      document.getElementById('trendChartFallback').style.display = 'block';
      if (!isAll) {
        document.getElementById('donutChartFallback').style.display = 'block';
        renderDonutLegendStats(data.summary);
      }
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

    // 数据集：全景 = 按模型堆叠色段；单 Agent = 保持 Input/Cache/Output + 费用折线原口径
    const modelStack = isAll ? buildModelStackSeries(trend) : null;
    let datasets;
    if (isAll) {
      datasets = modelStack ? modelStack.datasets : [{
        // byDate 缺失时的兜底：不虚构模型归属，仅展示当日总量
        label: '全部 Token',
        data: trend.map(t => (t.outputTokens || 0) + (t.inputTokens || 0) + (t.cacheTokens || 0)),
        backgroundColor: '#6366f1',
        stack: 'tokens',
        yAxisID: 'y',
        borderWidth: 0,
        maxBarThickness: 48
      }];
    } else {
      const outputTokens = trend.map(t => t.outputTokens);
      const inputTokens = trend.map(t => t.inputTokens);
      const cacheTokens = trend.map(t => t.cacheTokens);
      const costData = trend.map(t => {
        const c = calcCost(model, t.inputTokens, t.cacheTokens, t.outputTokens);
        return Number(toCnyCost(model, c).toFixed(2));
      });
      datasets = [
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
      ];
    }

    // 每日总量（直接对堆叠数据集求和，保证柱顶标签与柱高严格一致）
    const dayTotals = isAll
      ? labels.map((_, i) => datasets.reduce((acc, ds) => acc + (ds.data[i] || 0), 0))
      : null;

    el.trendChartTitle.textContent = isAll
      ? `全平台 Agent 每日 Token 消耗趋势 · 按模型分布`
      : (data.mode === 'daily' 
          ? `${data.displayName} 每日 Token 消耗趋势与等效费用走向 (CNY ¥)`
          : `${data.displayName} 会话活跃分布与费用统计 (CNY ¥)`);

    // 图例与右侧费用轴随视图切换：全景 = 动态模型图例、无费用轴
    if (trendLegendStaticHtml === null && el.trendChartLegend) {
      trendLegendStaticHtml = el.trendChartLegend.innerHTML;
    }
    if (el.trendYAxisRight) el.trendYAxisRight.style.display = isAll ? 'none' : '';
    if (el.trendChartLegend) {
      if (isAll) {
        const legendModels = modelStack ? modelStack.displayModels : [{ name: '全部 Token', color: '#6366f1' }];
        el.trendChartLegend.innerHTML = legendModels.map(m =>
          `<span class="legend-dot" style="background-color: ${m.color};"></span><span>${escapeHtml(m.name)}</span>`
        ).join('');
      } else {
        el.trendChartLegend.innerHTML = trendLegendStaticHtml;
      }
    }

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

    // 全景视图专用：柱顶绘制当日总量标签（口径 xxxM，小数省略；不足 1M 显示 <1M）
    const barTotalLabelPlugin = {
      id: 'barTotalLabels',
      afterDatasetsDraw(chart) {
        const yScale = chart.scales.y;
        const meta = chart.getDatasetMeta(0);
        if (!yScale || !meta || !meta.data || !dayTotals) return;
        const ctx = chart.ctx;
        ctx.save();
        ctx.font = `600 9px ${Chart.defaults.font.family}`;
        ctx.fillStyle = textColor;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        for (let i = 0; i < dayTotals.length; i++) {
          const total = dayTotals[i];
          if (!total) continue;
          const bar = meta.data[i];
          if (!bar) continue;
          const label = total >= 1e6 ? `${Math.floor(total / 1e6)}M` : '<1M';
          ctx.fillText(label, bar.x, yScale.getPixelForValue(total) - 3);
        }
        ctx.restore();
      }
    };

    // 悬浮卡片：全景 = 当日各模型消耗明细（按量降序、过滤零值）；单 Agent = 原口径
    const tooltipConfig = isAll ? {
      backgroundColor: isDark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.95)',
      titleColor: isDark ? '#f8fafc' : '#0f172a',
      bodyColor: isDark ? '#cbd5e1' : '#334155',
      borderColor: isDark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.1)',
      borderWidth: 1,
      padding: 12,
      boxPadding: 6,
      usePointStyle: true,
      filter: (item) => (item.raw || 0) > 0,
      itemSort: (a, b) => (b.raw || 0) - (a.raw || 0),
      callbacks: {
        title: function (items) {
          if (!items.length) return '';
          const idx = items[0].dataIndex;
          const d = trend[idx];
          return d ? `${d.date.slice(5)}(${d.weekday})  ${formatTokens(dayTotals[idx])}` : items[0].label;
        },
        label: function (ctx) {
          return ` ${ctx.dataset.label}: ${formatTokens(ctx.raw)}`;
        }
      }
    } : {
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
    };

    const trendScales = {
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
        // 全景视图预留柱顶标签头部空间
        grace: isAll ? '12%' : 0,
        ticks: {
          display: false // 隐藏内部画布刻度，固定于左侧固定列中展示
        }
      }
    };
    if (!isAll) {
      trendScales.yCost = {
        position: 'right',
        grid: { display: false },
        border: { display: false },
        ticks: {
          display: false // 隐藏内部画布刻度，固定于右侧固定列中展示
        }
      };
    }

    state.trendChartInstance = new Chart(el.trendChartCanvas, {
      type: 'bar',
      plugins: isAll ? [syncYAxisPlugin, barTotalLabelPlugin] : [syncYAxisPlugin],
      data: {
        labels: labels,
        datasets: datasets
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        // 顶部预留刻度标签空间，避免 grace 头部空间产生的最高刻度被固定轴容器裁切
        layout: isAll ? { padding: { top: 10 } } : undefined,
        animation: isAll ? { duration: 300 } : undefined,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: { display: false },
          tooltip: tooltipConfig
        },
        scales: trendScales
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

    // 全景视图已移除 Token 构成环形图：销毁可能残留的旧实例，释放内存后直接返回
    if (isAll) {
      if (state.donutChartInstance) {
        state.donutChartInstance.destroy();
        state.donutChartInstance = null;
      }
      return;
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
    dsh: { stroke: '#4d6bfe', bg: 'rgba(77, 107, 254, 0.15)', name: 'DeepSeek Harness' },
  };

  // 通用 Chart.js Y 轴刻度同步覆盖层组件
  function syncYAxisTicksOverlay(chart, overlayEl) {
    if (!chart || !chart.scales || !overlayEl) return;
    const yScale = chart.scales.y;
    if (!yScale || !Array.isArray(yScale.ticks)) return;
    let html = '';
    yScale.ticks.forEach(t => {
      const px = yScale.getPixelForValue(t.value);
      if (typeof px === 'number' && !isNaN(px)) {
        html += `<span class="y-axis-label y-axis-label-left" style="top:${px}px;">${formatTokens(t.value)}</span>`;
      }
    });
    overlayEl.innerHTML = html;
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
        syncYAxisTicksOverlay(chart, el.raceYAxisLeft);
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

  // ==========================================================================
  // 全模型每日用量走势折线图 (All Models Daily Trend Line Chart)
  // ==========================================================================

  function renderModelTrendLegend(displayModels, allData, modelsData) {
    if (!el.modelTrendLegendBar) return;
    let html = '';
    displayModels.forEach(m => {
      const isDimmed = state.highlightedModel && state.highlightedModel !== m.id;
      const isHighlighted = state.highlightedModel === m.id;

      let classes = 'race-legend-pill';
      if (isHighlighted) classes += ' highlighted';
      if (isDimmed) classes += ' dimmed';

      html += `
        <div class="${classes}" data-model="${escapeHtml(m.id)}" title="点击聚焦高亮 ${escapeHtml(m.name)} 折线，再次点击取消">
          <span class="race-legend-dot" style="background-color: ${m.color};"></span>
          <span>${escapeHtml(m.name)}</span>
          <span class="race-legend-val">${formatTokens(m.totalTokens)}</span>
        </div>
      `;
    });

    if (state.highlightedModel) {
      html += `
        <div class="race-legend-pill btn-reset-model-legend" style="border-style: dashed; color: var(--accent-blue);" title="还原所有折线">
          <span>↺ 还原全部</span>
        </div>
      `;
    }

    el.modelTrendLegendBar.innerHTML = html;

    el.modelTrendLegendBar.querySelectorAll('.race-legend-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        if (pill.classList.contains('btn-reset-model-legend')) {
          state.highlightedModel = null;
          renderModelTrendChart(allData, modelsData);
          return;
        }
        const mid = pill.getAttribute('data-model');
        if (state.highlightedModel === mid) {
          state.highlightedModel = null;
        } else {
          state.highlightedModel = mid;
        }
        renderModelTrendChart(allData, modelsData);
      });
    });
  }

  function renderModelTrendChart(allData, modelsData) {
    const dataToUse = modelsData || state.modelsData;
    const allDataToUse = allData || state.allAgentsData;
    if (!dataToUse || !dataToUse.byDate || typeof Chart === 'undefined') {
      if (el.modelTrendChartFallback) el.modelTrendChartFallback.style.display = 'block';
      return;
    }

    let trend = (allDataToUse && allDataToUse.dailyTrend) || [];
    if (state.modelTrendRange === '14') {
      trend = trend.slice(-14);
    } else if (state.modelTrendRange === '30') {
      trend = trend.slice(-30);
    }

    if (!trend.length) {
      if (el.modelTrendChartFallback) el.modelTrendChartFallback.style.display = 'block';
      return;
    }
    if (el.modelTrendChartFallback) el.modelTrendChartFallback.style.display = 'none';

    const byDate = (dataToUse && dataToUse.byDate) || {};

    // 复用已有的按时间范围聚合组件 aggregateModelsInRange (纯内存 O(N) 快速聚合)
    const startDate = trend[0].date;
    const endDate = trend[trend.length - 1].date;
    const aggregated = aggregateModelsInRange(startDate, endDate, byDate);

    const TOP_N = 8;
    const hasOthers = aggregated.length > TOP_N;
    const mainModels = hasOthers ? aggregated.slice(0, TOP_N) : aggregated;
    const otherModels = hasOthers ? aggregated.slice(TOP_N) : [];
    const otherNamesSet = new Set(otherModels.map(m => m.model));

    const displayModels = mainModels.map((m, idx) => ({
      id: m.model,
      name: m.model === 'unknown' ? 'unknown (异机/未指定)' : m.model,
      color: MODEL_SHARE_PALETTE[idx % MODEL_SHARE_PALETTE.length],
      totalTokens: m.totalTokens
    }));

    if (hasOthers) {
      const otherTokens = otherModels.reduce((acc, m) => acc + m.totalTokens, 0);
      if (otherTokens > 0) {
        displayModels.push({
          id: '__others__',
          name: `其他 (${otherModels.length} 款模型)`,
          color: MODEL_SHARE_REST_COLOR,
          totalTokens: otherTokens,
          isOthers: true
        });
      }
    }

    renderModelTrendLegend(displayModels, allDataToUse, dataToUse);

    const isDark = state.isDarkTheme;
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
    const textColor = isDark ? '#9ca3af' : '#475569';

    if (state.modelTrendChartInstance) {
      state.modelTrendChartInstance.destroy();
      state.modelTrendChartInstance = null;
    }

    const totalDays = trend.length;
    const labels = trend.map(t => t.date.slice(5) + `(${t.weekday})`);

    const viewportWidth = (el.modelTrendScrollViewport && el.modelTrendScrollViewport.clientWidth > 0)
      ? el.modelTrendScrollViewport.clientWidth
      : 600;

    if (totalDays > 30) {
      const dayWidth = Math.max(34, Math.floor(viewportWidth / 30));
      const totalWidth = Math.round(totalDays * dayWidth);
      if (el.modelTrendScrollCanvasWrap) {
        el.modelTrendScrollCanvasWrap.style.width = `${totalWidth}px`;
      }
    } else {
      if (el.modelTrendScrollCanvasWrap) {
        el.modelTrendScrollCanvasWrap.style.width = '100%';
      }
    }

    const datasets = [];
    displayModels.forEach(m => {
      const isHighlighted = state.highlightedModel === m.id;
      const isDimmed = state.highlightedModel && state.highlightedModel !== m.id;

      const lineData = trend.map(t => {
        const dayList = byDate[t.date] || [];
        if (m.isOthers) {
          let sum = 0;
          dayList.forEach(item => {
            const mod = item.model || 'unknown';
            if (otherNamesSet.has(mod)) {
              sum += (item.totalTokens || 0);
            }
          });
          return sum;
        } else {
          const found = dayList.find(item => (item.model || 'unknown') === m.id);
          return found ? (found.totalTokens || 0) : 0;
        }
      });

      datasets.push({
        label: m.name,
        modelId: m.id,
        data: lineData,
        borderColor: isDimmed ? 'rgba(156, 163, 175, 0.22)' : m.color,
        backgroundColor: m.color,
        borderWidth: isHighlighted ? 3.5 : (isDimmed ? 1.0 : 2.2),
        pointBackgroundColor: isDimmed ? 'rgba(156, 163, 175, 0.22)' : m.color,
        pointBorderColor: isDark ? '#1e293b' : '#ffffff',
        pointBorderWidth: 1.5,
        pointRadius: isHighlighted ? 4.5 : (isDimmed ? 1.0 : 3),
        pointHoverRadius: 6,
        tension: 0.25,
        fill: false,
        order: isHighlighted ? 1 : 10
      });
    });

    const syncModelTrendYAxisPlugin = {
      id: 'syncModelTrendYAxisOverlays',
      afterLayout: (chart) => {
        syncYAxisTicksOverlay(chart, el.modelTrendYAxisLeft);
      }
    };

    state.modelTrendChartInstance = new Chart(el.modelTrendChartCanvas, {
      type: 'line',
      plugins: [syncModelTrendYAxisPlugin],
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
                if (val <= 0 && state.highlightedModel !== ctx.dataset.modelId) {
                  return null;
                }
                return ` ${ctx.dataset.label}: ${formatTokens(val)}`;
              },
              footer: function (items) {
                const activeItems = items.filter(it => (it.raw || 0) > 0);
                const total = activeItems.reduce((acc, c) => acc + (c.raw || 0), 0);
                return total > 0 ? `当日全模型总计: ${formatTokens(total)}` : '';
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

    if (totalDays > 30 && el.modelTrendScrollViewport) {
      setTimeout(() => {
        if (el.modelTrendScrollViewport) {
          const maxScroll = el.modelTrendScrollViewport.scrollWidth - el.modelTrendScrollViewport.clientWidth;
          el.modelTrendScrollViewport.scrollLeft = maxScroll;
        }
      }, 50);
    }
  }

  // ==========================================================================
  // 全模型份额占比圆环图 (All Models Share Donut Chart)
  // ==========================================================================

  function renderModelDonutChart(allData, modelsData) {
    const dataToUse = modelsData || state.modelsData;
    const allDataToUse = allData || state.allAgentsData;
    if (!dataToUse || !dataToUse.byDate || !el.modelDonutChartCanvas || typeof Chart === 'undefined') {
      if (el.modelDonutFallback) el.modelDonutFallback.style.display = 'block';
      return;
    }

    const daily = (allDataToUse && allDataToUse.dailyTrend) || [];
    if (!daily.length) {
      if (el.modelDonutFallback) el.modelDonutFallback.style.display = 'block';
      return;
    }
    if (el.modelDonutFallback) el.modelDonutFallback.style.display = 'none';

    const byDate = dataToUse.byDate || {};
    const latestDate = daily[daily.length - 1].date;
    let startDate = latestDate;

    if (state.modelDonutRange === 'today') {
      startDate = latestDate;
      if (el.modelDonutSubtitle) el.modelDonutSubtitle.textContent = `📅 今日 (${latestDate}) 各模型用量分布`;
    } else if (state.modelDonutRange === '7') {
      startDate = daily[Math.max(0, daily.length - 7)].date;
      if (el.modelDonutSubtitle) el.modelDonutSubtitle.textContent = `📅 近 7 天 (${startDate} ~ ${latestDate})`;
    } else if (state.modelDonutRange === '14') {
      startDate = daily[Math.max(0, daily.length - 14)].date;
      if (el.modelDonutSubtitle) el.modelDonutSubtitle.textContent = `📅 近 14 天 (${startDate} ~ ${latestDate})`;
    } else if (state.modelDonutRange === '30') {
      startDate = daily[Math.max(0, daily.length - 30)].date;
      if (el.modelDonutSubtitle) el.modelDonutSubtitle.textContent = `📅 近 30 天 (${startDate} ~ ${latestDate})`;
    }

    // 复用已有的按时间范围聚合组件 aggregateModelsInRange (纯内存 O(N) 快速聚合)
    const aggregated = aggregateModelsInRange(startDate, latestDate, byDate);
    const totalTokens = aggregated.reduce((acc, m) => acc + (m.totalTokens || 0), 0);

    if (totalTokens <= 0) {
      if (el.modelDonutFallback) el.modelDonutFallback.style.display = 'block';
      if (el.modelDonutStats) el.modelDonutStats.innerHTML = '<div class="empty-state">所选时段暂无模型用量记录</div>';
      if (state.modelDonutChartInstance) {
        state.modelDonutChartInstance.destroy();
        state.modelDonutChartInstance = null;
      }
      return;
    }

    const TOP_N = 6;
    const hasOthers = aggregated.length > TOP_N;
    const mainModels = hasOthers ? aggregated.slice(0, TOP_N) : aggregated;
    const otherModels = hasOthers ? aggregated.slice(TOP_N) : [];

    const donutItems = mainModels.map((m, idx) => ({
      name: m.model === 'unknown' ? 'unknown (未指定)' : m.model,
      tokens: m.totalTokens,
      color: MODEL_SHARE_PALETTE[idx % MODEL_SHARE_PALETTE.length],
      pct: ((m.totalTokens / totalTokens) * 100).toFixed(1)
    }));

    if (hasOthers) {
      const otherTokens = otherModels.reduce((acc, m) => acc + m.totalTokens, 0);
      if (otherTokens > 0) {
        donutItems.push({
          name: `其他 (${otherModels.length} 款模型)`,
          tokens: otherTokens,
          color: MODEL_SHARE_REST_COLOR,
          pct: ((otherTokens / totalTokens) * 100).toFixed(1)
        });
      }
    }

    // 渲染右侧 Stats 条目
    if (el.modelDonutStats) {
      let statsHtml = '';
      donutItems.forEach(item => {
        statsHtml += `
          <div class="model-donut-stat-item" title="${escapeHtml(item.name)}: ${formatTokens(item.tokens)} (${item.pct}%)">
            <div class="model-donut-stat-header">
              <span class="model-donut-stat-name">
                <span class="legend-dot" style="background-color: ${item.color};"></span>
                <span>${escapeHtml(item.name)}</span>
              </span>
              <span class="model-donut-stat-val">${item.pct}% <span style="font-weight:400;opacity:0.75;font-size:0.7rem;">(${formatTokens(item.tokens)})</span></span>
            </div>
            <div class="model-donut-stat-bar">
              <div class="model-donut-stat-fill" style="width: ${item.pct}%; background-color: ${item.color};"></div>
            </div>
          </div>
        `;
      });
      el.modelDonutStats.innerHTML = statsHtml;
    }

    // 渲染 Chart.js Doughnut 环形图
    if (state.modelDonutChartInstance) {
      state.modelDonutChartInstance.destroy();
      state.modelDonutChartInstance = null;
    }

    const isDark = state.isDarkTheme;

    state.modelDonutChartInstance = new Chart(el.modelDonutChartCanvas, {
      type: 'doughnut',
      data: {
        labels: donutItems.map(d => d.name),
        datasets: [{
          data: donutItems.map(d => d.tokens),
          backgroundColor: donutItems.map(d => d.color),
          borderWidth: 1.5,
          borderColor: isDark ? '#1e293b' : '#ffffff',
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '66%',
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: isDark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.95)',
            titleColor: isDark ? '#f8fafc' : '#0f172a',
            bodyColor: isDark ? '#cbd5e1' : '#334155',
            borderColor: isDark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.1)',
            borderWidth: 1,
            padding: 10,
            boxPadding: 4,
            usePointStyle: true,
            callbacks: {
              label: function (ctx) {
                const val = ctx.raw || 0;
                const p = totalTokens > 0 ? ((val / totalTokens) * 100).toFixed(1) : 0;
                return ` ${ctx.label}: ${formatTokens(val)} (${p}%)`;
              }
            }
          }
        }
      }
    });
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
      let costDisplay = formatInlineCost(model, aCost);
      if (a.id === 'workbuddy' && a.credit > 0) {
        costDisplay += ` · <span style="color:var(--accent-pink,#f43f5e);">${a.credit.toFixed(1)}积</span>`;
      }
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
            <span class="agent-cost-num">${costDisplay}</span>
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

    // 7) 渲染全模型每日用量走势折线图与份额环形图
    if (state.modelsData) {
      renderModelTrendChart(allData, state.modelsData);
      renderModelDonutChart(allData, state.modelsData);
    }
  }

  // 4. 账本/项目列表渲染与过滤

  // ------------------------------------------------------------------------
  // 4.0 模型维度视图 (Models)
  //
  // 数据源：/api/models（与 /api/data 同源同口径；同步分片按设计不携带模型明细，
  // 故异机会话统一归入 unknown，既不虚构归属又保证总量一致）。
  //
  // 时间范围过滤在**前端**基于 byDate 求子集完成：后端保证「遍历 byDate 求和恒等于
  // models 合计」，且 byDate 已按「日期 × 模型 × 来源 Agent」切好，
  // 因此切换时间范围是零网络请求的纯内存聚合，即时响应。
  //
  // 计价口径：
  //   · equivalent（等效计价 / 原始）：统一按当前选中的计价模型费率折算，
  //     与页面其它位置的费用口径完全一致，便于横向比较。
  //   · unit（按模型单价）：每个模型按其自身费率计费，费率取自费率表
  //     （内置预设 ∪ 用户在「⚙️ 费率表」中自定义/导入的条目）；未匹配到费率时
  //     显式标注「费率未配置」并排除在费用合计之外，绝不虚构价格。
  // ------------------------------------------------------------------------
  const MODEL_SHARE_PALETTE = [
    '#4285f4', '#f59e0b', '#10b981', '#06b6d4', '#ec4899',
    '#8b5cf6', '#6366f1', '#f43f5e', '#14b8a6', '#eab308'
  ];
  const MODEL_SHARE_TOP_N = 8;
  const MODEL_SHARE_REST_COLOR = '#64748b';
  const MODEL_SHARE_UNKNOWN_COLOR = '#94a3b8';

  function formatTaskModelBadge(r) {
    const mName = r.modelName || 'unknown';
    if (!mName || mName === 'unknown') {
      return '<span class="task-model-badge cell-muted">—</span>';
    }
    const lower = mName.toLowerCase();
    let badgeClass = '';
    if (lower.includes('deepseek')) badgeClass = 'badge-deepseek';
    else if (lower.includes('gemini')) badgeClass = 'badge-gemini';
    else if (lower.includes('claude')) badgeClass = 'badge-claude';
    else if (lower.includes('gpt') || lower.includes('codex')) badgeClass = 'badge-gpt';
    else if (lower.includes('grok')) badgeClass = 'badge-grok';
    else if (lower.includes('glm')) badgeClass = 'badge-glm';

    const modelsMap = r.models || {};
    const modelKeys = Object.keys(modelsMap);
    let titleTip = `主模型: ${mName}`;
    let extraTag = '';
    if (modelKeys.length > 1) {
      extraTag = ` <span style="opacity:0.8;font-size:0.68rem;">+${modelKeys.length - 1}</span>`;
      const detailLines = modelKeys.map(k => `${k}: ${formatTokens(modelsMap[k].totalTokens || 0)} Tokens`);
      titleTip = `包含多模型调用:\n${detailLines.join('\n')}`;
    }

    return `<span class="task-model-badge ${badgeClass}" title="${escapeHtml(titleTip)}">${escapeHtml(mName)}${extraTag}</span>`;
  }

  function toDateStr(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  function shiftDateStr(baseStr, days) {
    const d = new Date(`${baseStr}T00:00:00`);
    d.setDate(d.getDate() + days);
    return toDateStr(d);
  }

  // 数据实际覆盖的日期边界（取自 byDate 的键），用于「全部历史」与日期选择器可选范围
  function getModelDateBounds() {
    const keys = Object.keys((state.modelsData && state.modelsData.byDate) || {});
    if (!keys.length) {
      const t = toDateStr(new Date());
      return { min: t, max: t };
    }
    keys.sort();
    return { min: keys[0], max: keys[keys.length - 1] };
  }

  // 把「时间范围」解析为具体起止日期（YYYY-MM-DD 字符串可直接比较，天然有序）
  function resolveModelRange() {
    const bounds = getModelDateBounds();
    const today = toDateStr(new Date());
    if (state.modelRange === 'today') return { start: today, end: today, label: '当天' };
    if (state.modelRange === '30d') return { start: shiftDateStr(today, -29), end: today, label: '近 30 天' };
    if (state.modelRange === 'all') return { start: bounds.min, end: bounds.max, label: '全部历史' };
    if (state.modelRange === 'custom') {
      const s = state.modelStart || bounds.min;
      const e = state.modelEnd || bounds.max;
      // 容错：用户可能把起止填反
      return s <= e
        ? { start: s, end: e, label: `${s} ~ ${e}` }
        : { start: e, end: s, label: `${e} ~ ${s}` };
    }
    return { start: shiftDateStr(today, -6), end: today, label: '近 7 天' };
  }

  // 归一化费率键：仅保留字母与数字并转小写。
  // 目的是让「实际模型名」与「费率表条目的 id / 显示名」能对上，例如
  //   gemini-3.8-flash  ←→  Gemini 3.8 Flash      （显示名带空格 / 大小写差异）
  //   deepseek-v4.1-flash ←→ DeepSeek-V4.1-Flash (高峰期)  （显示名带中文括注）
  // 注意：正因为要剥掉括注，高峰期/低谷期这类同源条目的归一化键会相同，
  // 故此类歧义情形必须判为「未匹配」而不是猜一个，避免用错价格。
  function normalizeRateKey(s) {
    return String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  }

  // 按模型名从费率表匹配费率（内置预设 ∪ 用户自定义/导入）：
  // ① id 精确 → ② id 忽略大小写 → ③ 归一化后匹配 id 或显示名（仅唯一命中时采纳）。
  // ③ 是必需的：既有「智能导入」流程给新条目生成的是 `model_<时间戳>` 形式的合成 id，
  // 永远不会等于真实模型名，因此只能靠显示名对上。
  function findRateForModel(modelName) {
    const all = getAllPricingModels();
    if (all[modelName]) return all[modelName];

    const lower = String(modelName || '').toLowerCase();
    const byId = Object.keys(all).find(k => k.toLowerCase() === lower);
    if (byId) return all[byId];

    const target = normalizeRateKey(modelName);
    if (!target) return null;
    const candidates = [];
    for (const k in all) {
      if (normalizeRateKey(k) === target || normalizeRateKey(all[k].name) === target) {
        candidates.push(all[k]);
      }
    }
    return candidates.length === 1 ? candidates[0] : null;
  }

  // 在 [start, end] 内按模型聚合（纯内存求和，无网络请求、无文件扫描）
  function aggregateModelsInRange(start, end, customByDate) {
    const byDate = customByDate || (state.modelsData && state.modelsData.byDate) || {};
    const map = new Map();
    for (const d in byDate) {
      if (d < start || d > end) continue;
      const list = byDate[d];
      for (let i = 0; i < list.length; i++) {
        const m = list[i];
        let e = map.get(m.model);
        if (!e) {
          e = {
            model: m.model,
            inputTokens: 0,
            cacheReadTokens: 0,
            outputTokens: 0,
            totalTokens: 0,
            calls: 0,
            credit: 0.0,
            modelMs: 0,
            agents: {}
          };
          map.set(m.model, e);
        }
        e.inputTokens += m.inputTokens || 0;
        e.cacheReadTokens += m.cacheReadTokens || 0;
        e.outputTokens += m.outputTokens || 0;
        e.totalTokens += m.totalTokens || 0;
        e.calls += m.calls || 0;
        if (m.credit) {
          e.credit = Math.round(((e.credit || 0) + Number(m.credit)) * 10000) / 10000;
        }
        if (m.modelMs) {
          e.modelMs = (e.modelMs || 0) + Number(m.modelMs);
        }
        const ags = m.agents;
        if (ags) {
          for (const aid in ags) {
            const src = ags[aid];
            const dst = e.agents[aid] || (e.agents[aid] = { totalTokens: 0, calls: 0, credit: 0.0, modelMs: 0 });
            dst.totalTokens += src.totalTokens || 0;
            dst.calls += src.calls || 0;
            if (src.credit) {
              dst.credit = Math.round(((dst.credit || 0) + Number(src.credit)) * 10000) / 10000;
            }
            if (src.modelMs) {
              dst.modelMs = (dst.modelMs || 0) + Number(src.modelMs);
            }
          }
        }
      }
    }
    return Array.from(map.values()).sort((a, b) => b.totalTokens - a.totalTokens);
  }

  // ==================================================================
  // 深度分析视图 (Insights)
  //
  // 面向「上报了丰富运行指标」的 Agent（当前为 DeepSeek Harness）。数据来自
  // /api/insights，全部由适配器在解析事件日志时顺带产出，**不额外扫描任何文件**，
  // 也不做第二次解压 —— 因此切到这个 tab 的代价与 /api/data 同量级。
  //
  // 与模型维度视图一致，这里刻意不复用账本的 KPI/趋势图：它的口径是
  // 「引擎级运行质量」（TPS / 首字延迟 / 思考–工具耗时结构 / 工具使用画像），
  // 与 Token 账本无关，混排会误导。
  // ==================================================================

  // 探测某 Agent 是否具备深度分析能力（结果缓存，避免每次点 tab 都请求）
  async function probeInsights(agentId) {
    if (!agentId || agentId === 'all') return false;
    if (state.insightsCapable.has(agentId)) return state.insightsCapable.get(agentId);
    let capable = false;
    try {
      const res = await fetch(`/api/insights?agent=${encodeURIComponent(agentId)}`, { cache: 'no-store' });
      const json = await res.json();
      if (json && json.available) {
        capable = true;
        state.insightsData = json;
      }
    } catch (_) {
      // 探测失败视为不支持，静默隐藏 tab（不阻塞主链路）
    }
    state.insightsCapable.set(agentId, capable);
    return capable;
  }

  // 根据当前 Agent 决定是否显示「深度分析」tab；若当前正处于该 tab 而能力消失，回退到日记账
  async function syncInsightsTab() {
    const capable = await probeInsights(state.agent);
    if (el.tabInsights) el.tabInsights.style.display = capable ? '' : 'none';
    if (!capable && state.mode === 'insights') {
      state.mode = 'daily';
      document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-mode') === 'daily');
      });
    }
  }

  async function loadAndRenderInsights() {
    el.insightsHeadbar.innerHTML = '';
    el.insightsKpiGrid.innerHTML = '';
    el.insightsToolPanel.innerHTML = '';
    el.insightsSessionPanel.innerHTML = '';
    el.insightsGapsPanel.innerHTML = `
      <div class="loading-state">
        <div class="spinner"></div>
        <p>正在汇总运行指标...</p>
      </div>
    `;

    try {
      const res = await fetch(`/api/insights?agent=${encodeURIComponent(state.agent)}`, { cache: 'no-store' });
      const json = await res.json();
      if (json.error) throw new Error(json.error);
      if (!json.available) {
        el.insightsGapsPanel.innerHTML = `<div class="empty-state">该 Agent 暂不支持深度分析。</div>`;
        return;
      }
      state.insightsData = json;
      state.insightsCapable.set(state.agent, true);
      renderInsightsView(json);
    } catch (err) {
      el.insightsGapsPanel.innerHTML =
        `<div class="empty-state">⚠️ 无法加载深度指标: ${escapeHtml(err.message)}</div>`;
    }
  }

  // 毫秒 → 人类可读（与 CLI format_ms_duration 保持同一套口径）
  function fmtMs(ms) {
    if (!ms || ms <= 0) return '--';
    return formatMsDuration(ms);
  }

  // 单个 KPI 卡片（复用既有 .kpi-card 结构，保证与账本视图观感一致）
  function kpiCard(title, badge, value, sub, cls) {
    return `
      <div class="kpi-card${cls ? ' ' + cls : ''}">
        <div class="kpi-header">
          <span class="kpi-title">${escapeHtml(title)}</span>
          <span class="kpi-badge ${cls === 'highlight-card' ? 'badge-green' : 'badge-blue'}">${escapeHtml(badge)}</span>
        </div>
        <div class="kpi-value">${value}</div>
        <div class="kpi-sub">${sub}</div>
      </div>
    `;
  }

  function renderInsightsView(data) {
    const t = data.totals || {};

    // ---- 顶部说明条：后端解码链路 + 会话数 ----
    el.insightsHeadbar.innerHTML = `
      <div class="insights-headline">
        <span class="insights-headline-title">⚡ ${escapeHtml(data.displayName || '运行深度分析')}</span>
        <span class="badge badge-subtle" title="Zstandard 多帧解码后端">解码内核：${escapeHtml(data.backend || '-')}</span>
        <span class="badge badge-subtle">${t.sessions || 0} 个会话 · ${t.turns || 0} 轮 · ${t.steps || 0} 步 · ${t.toolCalls || 0} 次工具调用</span>
        ${data.contextWindow ? `<span class="badge badge-subtle">上下文窗口 ${formatTokens(data.contextWindow)}</span>` : ''}
      </div>
      <p class="insights-headline-hint">
        口径来自本地事件日志的逐步结算记录，与账本 Token 同源；耗时类指标为模型实测时间戳差值。
      </p>
    `;

    // ---- KPI 网格 ----
    const tps = t.avgTps > 0 ? `${t.avgTps} tok/s` : '--';
    const hitRate = (t.cacheHitRate || 0).toFixed(1) + '%';

    el.insightsKpiGrid.innerHTML = [
      kpiCard('生成速率 TPS', '纯解码口径', tps,
        `解码 ${fmtMs(t.decodeMs)} · ${formatTokens(t.decodeTokens)} 输出 Token`),
      kpiCard('首字延迟 TTFT', '平均', t.avgTtftMs > 0 ? `${t.avgTtftMs} ms` : '--',
        `累计 ${fmtMs(t.ttftMs)} / ${t.steps || 0} 步`),
      kpiCard('单步推理耗时', 'LLM 端到端', t.avgLlmMs > 0 ? `${t.avgLlmMs} ms` : '--',
        `累计 ${fmtMs(t.llmMs)}`),
      kpiCard('工具执行耗时', '平均每次', t.avgToolMs > 0 ? `${t.avgToolMs} ms` : '--',
        `累计 ${fmtMs(t.toolMs)} / ${t.toolCalls || 0} 次`),
      kpiCard('缓存命中率', 'Prompt 节省', hitRate,
        `Cache ${formatTokens(t.cacheReadTokens)} / Input ${formatTokens(t.inputTokens)}`),
      kpiCard('调用规模', '模型交互', `${t.calls || 0}`,
        `${formatTokens(t.totalTokens)} Token 总量`),
      kpiCard('稳定性', '重试 / 中断', `${t.retries || 0} / ${t.interrupted || 0}`,
        `压缩 ${t.compactions || 0} 次`),
      kpiCard('思考-工具比', '耗时结构', (() => {
        const denom = (t.llmMs || 0) + (t.toolMs || 0);
        if (denom <= 0) return '--';
        return ((t.llmMs / denom) * 100).toFixed(1) + '%';
      })(), `推理 ${fmtMs(t.llmMs)} · 工具 ${fmtMs(t.toolMs)}`, 'highlight-card'),
    ].join('');

    // ---- 工具使用画像 ----
    const tools = data.tools || [];
    el.insightsToolPanel.innerHTML = `
      <div class="insights-panel-title">🔧 工具使用画像</div>
      ${tools.length ? `
        <div class="insights-tool-bars">
          ${tools.map(tool => {
            const pct = t.toolCalls > 0 ? (tool.calls / t.toolCalls) * 100 : 0;
            return `
              <div class="insights-tool-row">
                <span class="insights-tool-name">${escapeHtml(tool.name)}</span>
                <span class="insights-tool-track"><span class="insights-tool-fill" style="width:${pct.toFixed(1)}%"></span></span>
                <span class="insights-tool-count">${tool.calls}</span>
              </div>
            `;
          }).join('')}
        </div>
      ` : '<div class="empty-state">暂无工具调用记录</div>'}
    `;

    // ---- 会话耗时结构表 ----
    const sessions = (data.sessions || []).slice(0, 12);
    el.insightsSessionPanel.innerHTML = `
      <div class="insights-panel-title">📊 会话运行结构（按 Token 降序 · Top ${sessions.length}）</div>
      ${sessions.length ? `
        <div class="session-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>会话</th>
                <th class="num">Token</th>
                <th class="num">轮/步</th>
                <th class="num">工具</th>
                <th class="num">LLM 耗时</th>
                <th class="num">工具耗时</th>
                <th class="num">TTFT</th>
                <th class="num">TPS</th>
              </tr>
            </thead>
            <tbody>
              ${sessions.map(s => {
                const sTps = s.decodeMs > 0 ? (s.decodeTokens / (s.decodeMs / 1000)).toFixed(0) + ' tok/s' : '--';
                const sTtft = s.steps > 0 ? (s.ttftMs / s.steps).toFixed(0) + ' ms' : '--';
                return `
                  <tr>
                    <td title="${escapeHtml(s.cwd || '')}">${escapeHtml(s.title || s.sessionId || '(未命名)')}</td>
                    <td class="num">${formatTokens(s.totalTokens)}</td>
                    <td class="num">${s.turns}/${s.steps}</td>
                    <td class="num">${s.toolCalls}</td>
                    <td class="num">${fmtMs(s.llmMs)}</td>
                    <td class="num">${fmtMs(s.toolMs)}</td>
                    <td class="num">${sTtft}</td>
                    <td class="num">${sTps}</td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      ` : '<div class="empty-state">暂无会话数据</div>'}
    `;

    // ---- 口径缺口（诚实上报，不虚构数值） ----
    const gaps = data.gaps || [];
    el.insightsGapsPanel.innerHTML = gaps.length ? `
      <div class="insights-panel-title">ℹ️ 口径说明与已知缺口</div>
      <ul class="insights-gaps-list">
        ${gaps.map(g => `<li>${escapeHtml(g)}</li>`).join('')}
      </ul>
    ` : '';
  }

  async function loadAndRenderModels() {
    el.modelSummaryBar.innerHTML = '';
    el.modelShareChart.innerHTML = '';
    el.modelTableWrap.innerHTML = `
      <div class="loading-state">
        <div class="spinner"></div>
        <p>正在聚合模型维度数据...</p>
      </div>
    `;
    try {
      const res = await fetch(`/api/models?agent=${state.agent}`, { cache: 'no-store' });
      const json = await res.json();
      if (json.error) throw new Error(json.error);
      state.modelsData = json;
      syncModelDateInputs();
      renderModelsView();
    } catch (err) {
      el.modelTableWrap.innerHTML = `<div class="empty-state">⚠️ 无法加载模型维度数据: ${escapeHtml(err.message)}</div>`;
    }
  }

  // 让日期选择器与实际数据边界对齐（仅在尚未初始化时写入默认值，之后尊重用户输入）
  function syncModelDateInputs() {
    if (!el.modelStartDate || !el.modelEndDate) return;
    const bounds = getModelDateBounds();
    [el.modelStartDate, el.modelEndDate].forEach(inp => {
      inp.min = bounds.min;
      inp.max = bounds.max;
    });
    if (!state.modelStart) state.modelStart = shiftDateStr(bounds.max, -6);
    if (!state.modelEnd) state.modelEnd = bounds.max;
    el.modelStartDate.value = state.modelStart;
    el.modelEndDate.value = state.modelEnd;
  }

  function renderModelsView() {
    if (!state.modelsData) return;

    const range = resolveModelRange();
    const rows = aggregateModelsInRange(range.start, range.end);

    if (!rows.length) {
      el.modelSummaryBar.innerHTML = '';
      el.modelShareChart.innerHTML = '';
      el.modelTableWrap.innerHTML = `
        <div class="empty-state">
          <p>📭 所选时间范围内（${escapeHtml(range.label)}）没有任何模型用量记录</p>
          <p class="empty-hint">可切换更长的范围，或选择「全部历史」。</p>
        </div>
      `;
      return;
    }

    const isUnit = state.modelPricingMode === 'unit';
    const basisModel = getActiveModel(); // 等效计价时统一使用当前选中的计价模型费率

    // 逐模型计价 + 汇总
    let totalTokens = 0, totalCalls = 0, totalCostCny = 0, missingRate = 0;
    let totalModelMs = 0, totalOutputTokens = 0;
    rows.forEach(r => {
      r.rate = isUnit ? findRateForModel(r.model) : basisModel;
      if (r.rate) {
        r.cost = calcCost(r.rate, r.inputTokens, r.cacheReadTokens, r.outputTokens);
        r.costCny = toCnyCost(r.rate, r.cost);
        totalCostCny += r.costCny;
      } else {
        r.cost = null;
        r.costCny = null;
        missingRate++;
      }
      totalTokens += r.totalTokens;
      totalCalls += r.calls;
      totalModelMs += (r.modelMs || 0);
      totalOutputTokens += (r.outputTokens || 0);
    });

    // 占比基数：Token 或 费用
    const useCost = state.modelShareBasis === 'cost';
    const basisOf = (r) => (useCost ? (r.costCny || 0) : r.totalTokens);
    const basisTotal = useCost ? totalCostCny : totalTokens;
    const pctOf = (r) => (basisTotal > 0 ? (basisOf(r) / basisTotal) * 100 : 0);

    renderModelSummaryBar(range, rows.length, totalTokens, totalCalls, totalCostCny, missingRate, isUnit, basisModel, useCost, totalModelMs, totalOutputTokens);
    renderModelShareChart(rows, pctOf, basisOf, basisTotal, useCost, missingRate);
    renderModelTable(rows, pctOf, isUnit);

    // 按模型单价模式下，把「还有多少模型没费率」直接显示在入口按钮上，避免用户找不到补录位置
    if (el.btnOpenRateManager) {
      el.btnOpenRateManager.textContent = (isUnit && missingRate > 0)
        ? `⚙️ 费率表 (${missingRate} 个待配置)`
        : '⚙️ 费率表';
    }
  }

  function renderModelSummaryBar(range, modelCount, totalTokens, totalCalls, totalCostCny, missingRate, isUnit, basisModel, useCost, totalModelMs, totalOutputTokens) {
    const pricingNote = isUnit
      ? `按模型单价计价（费率表${missingRate ? `，其中 ${missingRate} 个模型未配置费率` : ''}）`
      : `等效计价 · 统一按「${escapeHtml(basisModel.name)}」折算`;

    const tpsMeta = (totalModelMs > 0 && totalOutputTokens > 0)
      ? `<span>⚡ 纯耗时 ${formatMsDuration(totalModelMs)} · 均速 ${Math.round(totalOutputTokens / (totalModelMs / 1000))} tok/s</span>`
      : '';

    el.modelSummaryBar.innerHTML = `
      <div class="models-summary-item">
        <span class="ms-label">Token 合计</span>
        <span class="ms-value">${formatTokens(totalTokens)}</span>
      </div>
      <div class="models-summary-item">
        <span class="ms-label">费用合计</span>
        <span class="ms-value cny-color">¥${totalCostCny.toFixed(2)}</span>
      </div>
      <div class="models-summary-item">
        <span class="ms-label">调用次数</span>
        <span class="ms-value">${totalCalls.toLocaleString()}</span>
      </div>
      <div class="models-summary-item">
        <span class="ms-label">模型数</span>
        <span class="ms-value">${modelCount}</span>
      </div>
      <div class="models-summary-meta">
        <span>📅 实际区间 ${escapeHtml(range.start)} ~ ${escapeHtml(range.end)}</span>
        <span>${pricingNote}</span>
        ${tpsMeta}
        <span>占比按 ${useCost ? '费用' : 'Token'} 归一</span>
      </div>
    `;
  }

  // Top 模型占比堆叠条 + 图例（纯 CSS 实现，零图表库开销）
  function renderModelShareChart(rows, pctOf, basisOf, basisTotal, useCost, missingRate) {
    const ordered = [...rows].sort((a, b) => basisOf(b) - basisOf(a));
    const head = ordered.slice(0, MODEL_SHARE_TOP_N);
    const tail = ordered.slice(MODEL_SHARE_TOP_N);

    const segs = head.map((r, i) => ({
      label: r.model,
      pct: pctOf(r),
      color: r.model === 'unknown' ? MODEL_SHARE_UNKNOWN_COLOR : MODEL_SHARE_PALETTE[i % MODEL_SHARE_PALETTE.length]
    }));
    if (tail.length) {
      const rest = tail.reduce((s, r) => s + basisOf(r), 0);
      segs.push({
        label: `其他 ${tail.length} 个模型`,
        pct: basisTotal > 0 ? (rest / basisTotal) * 100 : 0,
        color: MODEL_SHARE_REST_COLOR
      });
    }

    const barHtml = segs.map(s =>
      `<div class="share-stack-seg" style="width:${Math.max(0, s.pct).toFixed(3)}%;background:${s.color}"
            title="${escapeHtml(s.label)} · ${s.pct.toFixed(1)}%"></div>`
    ).join('');

    const legendHtml = segs.map(s => `
      <div class="share-legend-item" title="${escapeHtml(s.label)}">
        <span class="share-legend-dot" style="background:${s.color}"></span>
        <span class="share-legend-name">${escapeHtml(s.label)}</span>
        <span class="share-legend-pct">${s.pct.toFixed(1)}%</span>
      </div>
    `).join('');

    const costBasisWarning = (useCost && missingRate > 0)
      ? `<div class="models-share-note">⚠️ ${missingRate} 个模型未配置费率、无成本数据，未参与费用占比归一。</div>`
      : '';

    el.modelShareChart.innerHTML = `
      <div class="models-share-head">
        <span class="models-share-title">模型占比分布（按${useCost ? '费用' : 'Token'}）</span>
        <span class="models-share-sub">Top ${head.length}${tail.length ? ` + 其他 ${tail.length} 个` : ''}</span>
      </div>
      <div class="share-stack">${barHtml}</div>
      <div class="share-legend">${legendHtml}</div>
      ${costBasisWarning}
    `;
  }

  function renderModelTable(rows, pctOf, isUnit) {
    const q = state.modelFilter;
    const visible = q ? rows.filter(r => String(r.model).toLowerCase().includes(q)) : rows;

    if (!visible.length) {
      el.modelTableWrap.innerHTML = `<div class="empty-state">🔍 未找到匹配「${escapeHtml(state.modelFilter)}」的模型</div>`;
      return;
    }

    const body = visible.map((r, idx) => {
      const pct = pctOf(r);
      const isUnknown = r.model === 'unknown';
      const agentIds = Object.keys(r.agents || {});
      const agentHtml = agentIds.length
        ? agentIds.map(aid => `<span class="badge badge-subtle" title="${escapeHtml((AGENT_COLORS[aid] || {}).name || aid)}">${escapeHtml(aid)}</span>`).join(' ')
        : '<span class="cell-muted">—</span>';

      const costHtml = r.rate
        ? formatLedgerCost(r.rate, r.cost)
        : '<span class="rate-missing" title="该模型未在费率表中配置单价，无法计价">费率未配置</span>';

      const rateHtml = r.rate
        ? `<span class="rate-triple" title="计价依据：${escapeHtml(r.rate.name)}">${r.rate.currency === 'USD' ? '$' : '¥'}${formatRate(r.rate.inputRate)} / ${r.rate.currency === 'USD' ? '$' : '¥'}${formatRate(r.rate.cacheRate)} / ${r.rate.currency === 'USD' ? '$' : '¥'}${formatRate(r.rate.outputRate)}</span>`
        : '<span class="cell-muted">—</span>';

      const tpsStr = (r.modelMs > 0 && r.outputTokens > 0)
        ? ` · ⚡ ${Math.round(r.outputTokens / (r.modelMs / 1000))} tok/s`
        : '';

      return `
        <tr class="${isUnknown ? 'row-unknown-model' : ''}">
          <td class="col-rank">${idx + 1}</td>
          <td class="col-model">
            <span class="model-name">${escapeHtml(r.model)}</span>
            ${isUnknown ? '<span class="badge badge-orange">未识别</span>' : ''}
          </td>
          <td class="col-tokens">
            <div class="tok-main">${formatTokens(r.totalTokens)}</div>
            <div class="tok-split">入 ${formatTokens(r.inputTokens)} · 缓 ${formatTokens(r.cacheReadTokens)} · 出 ${formatTokens(r.outputTokens)}${tpsStr}</div>
          </td>
          <td class="col-share">
            <div class="share-cell">
              <div class="share-bar"><div class="share-bar-fill" style="width:${Math.min(100, pct).toFixed(2)}%"></div></div>
              <span class="share-pct">${pct.toFixed(1)}%</span>
            </div>
          </td>
          <td class="col-cost">${costHtml}</td>
          <td class="col-rate">${rateHtml}</td>
          <td class="col-calls">${(r.calls || 0).toLocaleString()}</td>
          <td class="col-agents">${agentHtml}</td>
        </tr>
      `;
    }).join('');

    // 表尾注记：只解释真正发生的情况，避免无谓文案
    const notes = [];
    if (rows.some(r => r.model === 'unknown')) {
      notes.push('「未识别」包含多端同步而来的异机会话（同步分片按设计不携带模型明细）与本地无法解析出模型名的记录，已计入合计未剔除。');
    }
    if (isUnit && rows.some(r => !r.rate)) {
      notes.push('部分模型在费率表中没有对应条目，其「计价」列显示为「费率未配置」且未计入费用合计；可点击上方「⚙️ 费率表」新增或导入。');
    }

    el.modelTableWrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th class="col-rank">序号</th>
            <th class="col-model">模型名称</th>
            <th class="col-tokens">消耗量 (Token)</th>
            <th class="col-share">占比</th>
            <th class="col-cost">计价</th>
            <th class="col-rate">单价 (/1M 入·缓·出)</th>
            <th class="col-calls">调用次数</th>
            <th class="col-agents">来源 Agent</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
      ${notes.length ? `<div class="models-table-notes">${notes.map(n => `💡 ${n}`).join('<br/>')}</div>` : ''}
    `;
  }

  // 模型维度视图的控件绑定（一次性注册；数据侧仅在已加载后做重渲染）
  function bindModelViewEvents() {
    if (el.modelRangeSelect) {
      el.modelRangeSelect.addEventListener('change', () => {
        state.modelRange = el.modelRangeSelect.value;
        if (el.modelCustomRange) {
          el.modelCustomRange.style.display = state.modelRange === 'custom' ? 'flex' : 'none';
        }
        renderModelsView(); // 纯内存聚合，无需重新请求后端
      });
    }
    if (el.modelStartDate) {
      el.modelStartDate.addEventListener('change', () => {
        state.modelStart = el.modelStartDate.value;
        if (state.modelRange === 'custom') renderModelsView();
      });
    }
    if (el.modelEndDate) {
      el.modelEndDate.addEventListener('change', () => {
        state.modelEnd = el.modelEndDate.value;
        if (state.modelRange === 'custom') renderModelsView();
      });
    }
    if (el.modelPricingSelect) {
      el.modelPricingSelect.addEventListener('change', () => {
        state.modelPricingMode = el.modelPricingSelect.value;
        renderModelsView();
      });
    }
    if (el.modelShareBasisSelect) {
      el.modelShareBasisSelect.addEventListener('change', () => {
        state.modelShareBasis = el.modelShareBasisSelect.value;
        renderModelsView();
      });
    }
    if (el.modelFilterInput) {
      el.modelFilterInput.addEventListener('input', () => {
        state.modelFilter = el.modelFilterInput.value.trim().toLowerCase();
        renderModelsView();
      });
    }
    // 「费率表」入口：复用既有的计费模型管理弹窗（内含智能导入 / 新增 / 编辑 / 删除）
    if (el.btnOpenRateManager) {
      el.btnOpenRateManager.addEventListener('click', () => {
        if (state.modelPricingMode !== 'unit') {
          showToast('提示：切换到「按模型单价」后，费率表才会参与计价');
        }
        openModelManager();
      });
    }
  }

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
    const isWorkbuddy = (state.agent === 'workbuddy') || (state.data && state.data.agent === 'workbuddy') || (state.data && state.data.summary && state.data.summary.credit > 0);
    let rowsHtml = '';
    filtered.forEach((r, idx) => {
      const rCost = calcCost(model, r.inputTokens, r.cacheTokens, r.outputTokens);
      const creditHtml = isWorkbuddy
        ? `<td class="col-credit">${(r.creditRaw !== undefined ? r.creditRaw : (r.credit || 0)).toFixed(2)}</td>`
        : '';
      const tpsTip = (r.modelMs > 0 && r.outputTokens > 0)
        ? ` title="纯推理耗时: ${formatMsDuration(r.modelMs)}, 速率: ${Math.round(r.outputTokens / (r.modelMs / 1000))} tok/s"`
        : '';
      rowsHtml += `
        <tr>
          <td class="col-rank">${idx + 1}</td>
          <td class="col-time">${r.time || r.date || '--'}</td>
          <td class="col-tokens">${formatTokens(r.totalTokens)}</td>
          <td class="col-input">${formatTokens(r.inputTokens)}</td>
          <td class="col-output"${tpsTip}>${formatTokens(r.outputTokens)}</td>
          <td class="col-cache">${formatTokens(r.cacheTokens)}</td>
          <td class="col-hitrate">${calcHitRateStr(r.cacheTokens, r.inputTokens)}</td>
          <td class="col-task-model">${formatTaskModelBadge(r)}</td>
          ${creditHtml}
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

    const creditHeader = isWorkbuddy ? `<th class="col-credit">消耗积分</th>` : '';

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
              <th class="col-task-model">模型</th>
              ${creditHeader}
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
    const isWorkbuddy = (state.agent === 'workbuddy') || (state.data && state.data.agent === 'workbuddy') || (state.data && state.data.summary && state.data.summary.credit > 0);
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
          const creditHtml = isWorkbuddy
            ? `<td class="col-credit">${(r.creditRaw !== undefined ? r.creditRaw : (r.credit || 0)).toFixed(2)}</td>`
            : '';
          const tpsTip = (r.modelMs > 0 && r.outputTokens > 0)
            ? ` title="纯推理耗时: ${formatMsDuration(r.modelMs)}, 速率: ${Math.round(r.outputTokens / (r.modelMs / 1000))} tok/s"`
            : '';
          tableRows += `
            <tr>
              <td class="col-rank">${r.index}</td>
              <td class="col-time">${r.time}</td>
              <td class="col-tokens">${formatTokens(r.totalTokens)}</td>
              <td class="col-input">${formatTokens(r.inputTokens)}</td>
              <td class="col-output"${tpsTip}>${formatTokens(r.outputTokens)}</td>
              <td class="col-cache">${formatTokens(r.cacheTokens)}</td>
              <td class="col-hitrate">${calcHitRateStr(r.cacheTokens, r.inputTokens)}</td>
              <td class="col-task-model">${formatTaskModelBadge(r)}</td>
              ${creditHtml}
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
        const dayCreditStat = (isWorkbuddy && d.credit !== undefined)
          ? `<span>积分: <strong style="color:var(--accent-pink,#f43f5e);">${d.credit.toFixed(2)}积</strong></span>`
          : '';
        const tableCreditHeader = isWorkbuddy ? `<th class="col-credit">消耗积分</th>` : '';

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
                ${dayCreditStat}
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
                    <th class="col-task-model">模型</th>
                    ${tableCreditHeader}
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
        const weekCreditStat = (isWorkbuddy && w.credit !== undefined)
          ? `<span>积分: <strong style="color:var(--accent-pink,#f43f5e);">${w.credit.toFixed(2)}积</strong></span>`
          : '';
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
                ${weekCreditStat}
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
