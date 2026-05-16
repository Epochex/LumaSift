const topbar = document.querySelector(".topbar");
const steps = [...document.querySelectorAll(".step")];
const scoreBoard = document.querySelector(".score-board");
const parameterGrid = document.querySelector(".parameter-grid");
const sequenceDots = [...document.querySelectorAll(".sequence-index span")];
const photoStack = document.querySelector(".photo-stack");
const signalPanel = document.querySelector(".signal-panel");
const meter = document.querySelector(".meter");
const meterBar = document.querySelector(".meter span");
const decisionButtons = [...document.querySelectorAll(".decision-strip button[data-decision]")];
const thumbs = [...document.querySelectorAll(".thumb")];
const frames = [...document.querySelectorAll(".photo-frame[data-candidate]")];
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const candidates = {
  keep: {
    index: 0,
    count: "5 / 24",
    progress: 21,
    chips: { done: "完成 3", cache: "缓存 1", fail: "失败 0" },
    relation: "手势、视线和街道线索汇到同一动作。",
    moment: "动作峰值清楚，遮挡没有切断主体。",
    preserve: "保留颗粒、招牌和地面方向线。",
    ticker: "样例状态：压缩预览已完成，深评结论可复核。",
    note: "KEEP：故事证据强，技术瑕疵只作为后期恢复信号。",
    scores: { story: 94, moment: 87, structure: 82, risk: 41 },
    params: {
      exposure: ["+0.15", "轻提人物脸部，不洗掉夜色。"],
      contrast: ["+12", "强化人车边缘和街道压迫感。"],
      black: ["-8", "保留暗部重量，让环境成立。"],
      hsl: ["黄 -10", "压弱招牌溢色，避免抢主体。"],
      grade: ["阴影偏青", "把冷街景和暖标识拉开。"],
      mask: ["人物 +0.20", "只提关键动作区域，保留颗粒。"],
    },
  },
  maybe: {
    index: 1,
    count: "11 / 24",
    progress: 46,
    chips: { done: "完成 7", cache: "缓存 2", fail: "失败 0" },
    relation: "人物关系有苗头，但公交车块面切断主体。",
    moment: "动作拖影和遮挡让峰值不确定，需要同组复核。",
    preserve: "保留车窗遮挡边缘，它解释了 MAYBE 原因。",
    ticker: "样例状态：同组序列比对中，等待人工复核。",
    note: "MAYBE：不是删除，而是要求同组照片证明这一刻是否最好。",
    scores: { story: 72, moment: 58, structure: 68, risk: 63 },
    params: {
      exposure: ["+0.05", "只轻微提亮主体，避免让车体更抢眼。"],
      contrast: ["+6", "保留拖影，不把不确定性修成假锐。"],
      black: ["-4", "压住车窗暗面，维持遮挡证据。"],
      hsl: ["黄 -18", "降低复核提示区的招牌干扰。"],
      grade: ["中性偏冷", "让公交和人物分层，不制造戏剧化。"],
      mask: ["主体 +0.12", "仅在可见身体轮廓上做小范围提亮。"],
    },
  },
  reject: {
    index: 2,
    count: "18 / 24",
    progress: 75,
    chips: { done: "完成 14", cache: "缓存 2", fail: "失败 1" },
    relation: "主体被切到画面边缘，没有形成可读关系。",
    moment: "动作已经错过，中心区域只有空白和过曝块面。",
    preserve: "无需进入精修；只保留为淘汰样例和错误记录。",
    ticker: "样例状态：硬风险命中，跳过 Qwen 深度解释以节省成本。",
    note: "REJECT：不是因为不够锐，而是缺少故事主体且高光不可恢复。",
    scores: { story: 24, moment: 19, structure: 31, risk: 91 },
    params: {
      exposure: ["跳过", "高光发灰不可恢复，曝光不再投入。"],
      contrast: ["跳过", "提高对比只会放大空白和边缘瑕疵。"],
      black: ["跳过", "暗部信息不足，无法重建主体关系。"],
      hsl: ["跳过", "颜色不是主要问题，故事证据缺席。"],
      grade: ["不生成", "不为淘汰片生成风格化方案。"],
      mask: ["不生成", "主体缺失，局部蒙版没有有效目标。"],
    },
  },
};

let activeStepIndex = 0;
let activeCandidate = "keep";
let scoreAnimated = false;

function setActiveStep(index) {
  activeStepIndex = index;
  steps.forEach((step, stepIndex) => {
    const active = stepIndex === activeStepIndex;
    step.classList.toggle("is-active", active);
    step.setAttribute("aria-pressed", String(active));
  });
}

steps.forEach((step, index) => {
  step.addEventListener("mouseenter", () => setActiveStep(index));
  step.addEventListener("focus", () => setActiveStep(index));
  step.addEventListener("click", () => setActiveStep(index));
  step.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setActiveStep(index);
    }
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      steps[(index + 1) % steps.length]?.focus();
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      steps[(index - 1 + steps.length) % steps.length]?.focus();
    }
  });
});

window.addEventListener("scroll", () => {
  topbar?.classList.toggle("is-scrolled", window.scrollY > 24);
});

if ("IntersectionObserver" in window) {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        if (entry.target === scoreBoard) animateScores();
        revealObserver.unobserve(entry.target);
      });
    },
    { threshold: 0.24 },
  );

  steps.forEach((step) => revealObserver.observe(step));
  if (scoreBoard) revealObserver.observe(scoreBoard);
  if (parameterGrid) revealObserver.observe(parameterGrid);
} else {
  [...steps, scoreBoard, parameterGrid].filter(Boolean).forEach((node) => node.classList.add("is-visible"));
  animateScores();
}

function animateNumber(node, target) {
  if (reduceMotion) {
    node.textContent = String(target);
    return;
  }
  const from = Number(node.textContent || 0);
  const start = performance.now();
  const duration = 420;

  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    node.textContent = String(Math.round(from + (target - from) * eased));
    if (progress < 1) requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
}

function animateScores() {
  scoreAnimated = true;
  document.querySelectorAll("[data-value]").forEach((node) => {
    animateNumber(node, Number(node.getAttribute("data-value") || 0));
  });
}

function setText(selector, text) {
  const node = document.querySelector(selector);
  if (node) node.textContent = text;
}

function pulseSemanticChange() {
  if (reduceMotion) return;
  [photoStack, signalPanel, scoreBoard, parameterGrid].filter(Boolean).forEach((node) => {
    node.classList.remove("is-switching");
    void node.offsetWidth;
    node.classList.add("is-switching");
    window.setTimeout(() => node.classList.remove("is-switching"), 360);
  });
}

function setCandidate(candidateKey) {
  const candidate = candidates[candidateKey] || candidates.keep;
  activeCandidate = candidateKey;
  document.body.dataset.candidate = candidateKey;
  photoStack?.setAttribute("data-decision", candidateKey);

  decisionButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.decision === candidateKey));
  });

  thumbs.forEach((thumb) => {
    const active = thumb.dataset.candidate === candidateKey;
    thumb.classList.toggle("is-selected", active);
    thumb.setAttribute("aria-pressed", String(active));
  });

  frames.forEach((frame) => {
    frame.classList.toggle("is-active", frame.dataset.candidate === candidateKey);
  });

  sequenceDots.forEach((dot, index) => {
    dot.classList.toggle("is-current", index === candidate.index);
  });

  setText('[data-panel="count"]', candidate.count);
  setText('[data-panel="done"]', candidate.chips.done);
  setText('[data-panel="cache"]', candidate.chips.cache);
  setText('[data-panel="fail"]', candidate.chips.fail);
  setText('[data-panel="relation"]', candidate.relation);
  setText('[data-panel="moment"]', candidate.moment);
  setText('[data-panel="preserve"]', candidate.preserve);
  setText('[data-panel="ticker"]', candidate.ticker);
  setText('[data-panel="note"]', candidate.note);

  if (meter) meter.setAttribute("aria-valuenow", String(Math.round((candidate.progress / 100) * 24)));
  if (meterBar) meterBar.style.width = `${candidate.progress}%`;

  Object.entries(candidate.scores).forEach(([key, value]) => {
    const row = document.querySelector(`[data-score-key="${key}"]`);
    const valueNode = row?.querySelector("[data-value]");
    row?.style.setProperty("--score", value);
    valueNode?.setAttribute("data-value", String(value));
    if (valueNode && scoreAnimated) animateNumber(valueNode, value);
    if (valueNode && !scoreAnimated) valueNode.textContent = String(value);
  });

  Object.entries(candidate.params).forEach(([key, [value, description]]) => {
    const item = document.querySelector(`[data-param="${key}"]`);
    const valueNode = item?.querySelector("b");
    const detailNode = item?.querySelector("small");
    if (valueNode) valueNode.textContent = value;
    if (detailNode) detailNode.textContent = description;
  });

  pulseSemanticChange();
}

decisionButtons.forEach((button) => {
  button.addEventListener("click", () => setCandidate(button.dataset.decision || "keep"));
  button.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setCandidate(button.dataset.decision || "keep");
    }
  });
});

thumbs.forEach((thumb) => {
  thumb.addEventListener("click", () => setCandidate(thumb.dataset.candidate || "keep"));
});

setCandidate(activeCandidate);
