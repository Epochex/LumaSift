const topbar = document.querySelector(".topbar");
const railSteps = [...document.querySelectorAll(".rail-step")];
const flowCards = [...document.querySelectorAll(".flow-card")];
const workflowLabel = document.querySelector('[data-workflow="label"]');
const workflowStatus = document.querySelector('[data-workflow="status"]');
const photoStack = document.querySelector(".photo-stack");
const frames = [...document.querySelectorAll(".photo-frame[data-candidate]")];
const decisionButtons = [...document.querySelectorAll(".decision-strip button[data-decision]")];
const thumbs = [...document.querySelectorAll(".thumb[data-candidate]")];
const meter = document.querySelector(".meter");
const meterBar = document.querySelector(".meter span");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const particleCanvas = document.querySelector("[data-particle-field]");
const pointer = { x: 0.5, y: 0.5, active: false };
let activeWorkflow = "import";
const numberAnimations = new WeakMap();

const workflow = {
  import: ["01 / 选择照片目录", "读取预览图、文件路径和基础元数据"],
  local: ["02 / 本地快速初筛", "生成结构、亮度、相似组和恢复空间信号"],
  qwen: ["03 / 高价值候选深评", "把 Top-N 压缩预览送入 Qwen 深评队列"],
  edit: ["04 / 生成修图方案", "输出裁切、局部蒙版、HSL 和 Lightroom 参数"],
};

const candidates = {
  keep: {
    count: "5 / 24",
    progress: 21,
    chips: { done: "完成 3", cache: "缓存 1", fail: "失败 0" },
    relation: "手势、视线和街道线索汇到同一动作。",
    moment: "动作峰值清楚，遮挡没有切断主体。",
    preserve: "保留颗粒、招牌和地面方向线。",
    note: "KEEP：人物关系和瞬间成立，技术风险进入后期恢复项。",
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
    count: "11 / 24",
    progress: 46,
    chips: { done: "完成 7", cache: "缓存 2", fail: "失败 0" },
    relation: "人物关系有苗头，但公交车块面切断主体。",
    moment: "动作拖影和遮挡让峰值不确定，需要同组复核。",
    preserve: "保留车窗遮挡边缘，它解释了 MAYBE 原因。",
    note: "MAYBE：进入同组复核，检查相邻照片是否有更完整的动作峰值。",
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
    count: "18 / 24",
    progress: 75,
    chips: { done: "完成 14", cache: "缓存 2", fail: "失败 1" },
    relation: "主体被切到画面边缘，没有形成可读关系。",
    moment: "动作已经错过，中心区域只有空白和过曝块面。",
    preserve: "无需进入精修；只保留为淘汰样例和错误记录。",
    note: "REJECT：主体关系缺席，高光和边缘信息不足，停止生成修图方案。",
    scores: { story: 24, moment: 19, structure: 31, risk: 91 },
    params: {
      exposure: ["跳过", "高光发灰不可恢复，曝光不再投入。"],
      contrast: ["跳过", "提高对比只会放大空白和边缘瑕疵。"],
      black: ["跳过", "暗部信息不足，无法重建主体关系。"],
      hsl: ["跳过", "颜色调整无法补足主体关系和瞬间证据。"],
      grade: ["不生成", "不为淘汰片生成风格化方案。"],
      mask: ["不生成", "主体缺失，局部蒙版没有有效目标。"],
    },
  },
};

function setText(selector, value) {
  const node = document.querySelector(selector);
  if (node) node.textContent = value;
}

function pulse(...nodes) {
  if (reduceMotion) return;
  nodes.filter(Boolean).forEach((node) => {
    node.classList.remove("is-switching");
    void node.offsetWidth;
    node.classList.add("is-switching");
    window.setTimeout(() => node.classList.remove("is-switching"), 360);
  });
}

function animateNumber(node, nextValue) {
  if (!node) return;
  const animationId = (numberAnimations.get(node) || 0) + 1;
  numberAnimations.set(node, animationId);
  const startValue = Number(node.textContent) || 0;
  const delta = nextValue - startValue;
  const start = performance.now();
  node.classList.add("is-counting");

  const tick = (time) => {
    if (numberAnimations.get(node) !== animationId) return;
    const t = Math.min(1, (time - start) / 460);
    const eased = 1 - Math.pow(1 - t, 3);
    node.textContent = String(Math.round(startValue + delta * eased));
    if (t < 1 && !reduceMotion) {
      requestAnimationFrame(tick);
    } else {
      node.textContent = String(nextValue);
      window.setTimeout(() => node.classList.remove("is-counting"), 160);
    }
  };

  if (reduceMotion) {
    node.textContent = String(nextValue);
    node.classList.remove("is-counting");
  } else {
    requestAnimationFrame(tick);
  }
}

function setWorkflow(step) {
  const state = workflow[step] || workflow.import;
  activeWorkflow = step;
  document.body.dataset.workflow = step;
  if (workflowLabel) workflowLabel.textContent = state[0];
  if (workflowStatus) workflowStatus.textContent = state[1];
  railSteps.forEach((item) => item.classList.toggle("is-active", item.dataset.step === step));
  flowCards.forEach((item) => item.classList.toggle("is-active", item.dataset.stepCard === step));
  if (step === "import") setCandidate("keep", { light: true });
  if (step === "local") setCandidate("maybe", { light: true });
  if (step === "qwen") setCandidate("keep", { light: true });
  if (step === "edit") setCandidate("keep", { light: true });
  pulse(document.querySelector(".studio-screen"));
  window.dispatchEvent(new CustomEvent("lumasift:workflow", { detail: { step } }));
}

function setCandidate(candidateKey, options = {}) {
  const candidate = candidates[candidateKey] || candidates.keep;
  document.body.dataset.candidate = candidateKey;
  photoStack?.setAttribute("data-decision", candidateKey);
  frames.forEach((frame) => frame.classList.toggle("is-active", frame.dataset.candidate === candidateKey));
  decisionButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.decision === candidateKey));
  });
  thumbs.forEach((thumb) => {
    const active = thumb.dataset.candidate === candidateKey;
    thumb.classList.toggle("is-selected", active);
    thumb.setAttribute("aria-pressed", String(active));
  });

  setText('[data-panel="count"]', candidate.count);
  setText('[data-panel="done"]', candidate.chips.done);
  setText('[data-panel="cache"]', candidate.chips.cache);
  setText('[data-panel="fail"]', candidate.chips.fail);
  setText('[data-panel="relation"]', candidate.relation);
  setText('[data-panel="moment"]', candidate.moment);
  setText('[data-panel="preserve"]', candidate.preserve);
  setText('[data-panel="note"]', candidate.note);

  if (meter) meter.setAttribute("aria-valuenow", String(Math.round((candidate.progress / 100) * 24)));
  if (meterBar) meterBar.style.width = `${candidate.progress}%`;

  Object.entries(candidate.scores).forEach(([key, value]) => {
    const row = document.querySelector(`[data-score-key="${key}"]`);
    const valueNode = row?.querySelector("[data-value]");
    row?.style.setProperty("--score", value);
    if (valueNode) {
      valueNode.dataset.value = String(value);
      animateNumber(valueNode, value);
    }
  });

  Object.entries(candidate.params).forEach(([key, [value, description]]) => {
    const item = document.querySelector(`[data-param="${key}"]`);
    const valueNode = item?.querySelector("b");
    const detailNode = item?.querySelector("small");
    if (valueNode) valueNode.textContent = value;
    if (detailNode) detailNode.textContent = description;
    if (item && !reduceMotion) {
      item.classList.remove("is-updated");
      void item.offsetWidth;
      item.classList.add("is-updated");
    }
  });

  if (!options.light) {
    pulse(photoStack, document.querySelector(".signal-panel"), document.querySelector(".score-board"), document.querySelector(".parameter-grid"));
  }
}

function updateActiveNav() {
  topbar?.classList.toggle("is-scrolled", window.scrollY > 24);
  const sections = [...document.querySelectorAll("main > section[id]")];
  const current = sections.find((section) => {
    const rect = section.getBoundingClientRect();
    return rect.top <= 140 && rect.bottom > 140;
  });
  document.querySelectorAll(".topbar nav a").forEach((link) => {
    link.classList.toggle("is-current", current ? link.getAttribute("href") === `#${current.id}` : false);
  });
}

window.addEventListener("scroll", updateActiveNav, { passive: true });
window.addEventListener("resize", updateActiveNav);
window.addEventListener("hashchange", updateActiveNav);

railSteps.forEach((button) => button.addEventListener("click", () => setWorkflow(button.dataset.step || "import")));
flowCards.forEach((card) => {
  card.addEventListener("mouseenter", () => card.classList.add("is-preview"));
  card.addEventListener("mouseleave", () => card.classList.remove("is-preview"));
  card.addEventListener("click", () => setWorkflow(card.dataset.stepCard || "import"));
});
decisionButtons.forEach((button) => button.addEventListener("click", () => setCandidate(button.dataset.decision || "keep")));
thumbs.forEach((thumb) => thumb.addEventListener("click", () => setCandidate(thumb.dataset.candidate || "keep")));

setWorkflow("import");
setCandidate("keep");
updateActiveNav();

function createParticleField(canvas) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return;

  let width = 0;
  let height = 0;
  let dpr = 1;
  let particles = [];
  let frame = 0;
  let running = false;
  let visible = true;
  let canvasRect = canvas.getBoundingClientRect();
  let animationFrameId = 0;

  const noise = (x) => {
    const v = Math.sin(x * 12.9898) * 43758.5453;
    return v - Math.floor(v);
  };

  const rect = (x, y, left, top, right, bottom) => x >= left && x <= right && y >= top && y <= bottom;

  const inBand = (x, y, mode) => {
    const diagonal = Math.abs(y - (0.86 - x * 0.56)) < 0.035 && x > 0.03 && x < 0.96;
    const headlinePlate = rect(x, y, 0.02, 0.12, 0.72, 0.34);
    const evidencePlate = rect(x, y, 0.08, 0.47, 0.78, 0.66);
    const contactFloor = rect(x, y, 0.0, 0.73, 0.94, 0.92);
    const productGhost = rect(x, y, 0.46, 0.30, 0.95, 0.86);
    const rightScore = rect(x, y, 0.73, 0.16, 0.95, 0.72);
    const cropFrame =
      rect(x, y, 0.18, 0.24, 0.57, 0.65) &&
      (Math.abs(x - 0.18) < 0.014 || Math.abs(x - 0.57) < 0.014 || Math.abs(y - 0.24) < 0.018 || Math.abs(y - 0.65) < 0.018);

    if (mode === "local") {
      const clusterA = Math.hypot(x - 0.22, y - 0.42) < 0.18;
      const clusterB = Math.hypot(x - 0.48, y - 0.46) < 0.15;
      const clusterC = Math.hypot(x - 0.74, y - 0.5) < 0.18;
      return clusterA || clusterB || clusterC || contactFloor || diagonal;
    }
    if (mode === "qwen") {
      const evidenceBox = rect(x, y, 0.52, 0.20, 0.9, 0.62);
      const evidenceRay = Math.abs(y - (0.72 - x * 0.38)) < 0.03 && x > 0.12 && x < 0.9;
      return evidenceBox || evidenceRay || headlinePlate || cropFrame;
    }
    if (mode === "edit") {
      const parameterPanel = rect(x, y, 0.62, 0.19, 0.95, 0.82);
      const maskLane = Math.abs(x - 0.68) < 0.02 && y > 0.18 && y < 0.82;
      return parameterPanel || cropFrame || maskLane || diagonal || contactFloor;
    }
    return headlinePlate || evidencePlate || contactFloor || productGhost || rightScore || cropFrame || diagonal;
  };

  const build = () => {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    const nextRect = canvas.getBoundingClientRect();
    canvasRect = nextRect;
    width = Math.max(1, Math.floor(nextRect.width));
    height = Math.max(1, Math.floor(nextRect.height));
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const smallScreen = width < 680;
    const gap = smallScreen ? 15 : width > 1300 ? 8 : 10;
    const size = width > 1300 ? 4 : 3;
    const next = [];
    let index = 0;
    const mode = document.body.dataset.workflow || activeWorkflow || "import";

    for (let y = gap; y < height - gap; y += gap) {
      for (let x = gap; x < width - gap; x += gap) {
        const nx = x / width;
        const ny = y / height;
        if (!inBand(nx, ny, mode)) continue;

        const edge = noise(index + nx * 20 + ny * 40);
        const density = mode === "qwen" ? 0.62 : mode === "edit" ? 0.64 : nx < 0.42 ? 0.58 : nx > 0.66 ? 0.63 : 0.66;
        if (edge > density) continue;

        const redBias = mode === "qwen" || mode === "edit" ? 0.4 : nx < 0.45 ? 0.34 : 0.24;
        const cyanBias = mode === "local" ? 0.42 : nx > 0.62 ? 0.34 : 0.22;
        const warmBias = mode === "import" ? 0.26 : mode === "local" ? 0.34 : 0.2;
        next.push({
          x,
          y,
          ox: x,
          oy: y,
          s: size + Math.floor(noise(index + 8) * 2),
          a: 0.12 + noise(index + 3) * 0.54,
          phase: noise(index + 9) * Math.PI * 2,
          red: noise(index + 13) < redBias,
          cyan: noise(index + 17) < cyanBias,
          warm: noise(index + 19) < warmBias,
        });
        index += 1;
      }
    }

    particles = next;
  };

  const draw = (time) => {
    if (!running || !visible) return;
    frame = time * 0.001;
    ctx.clearRect(0, 0, width, height);

    for (const p of particles) {
      const dx = p.ox / width - pointer.x;
      const dy = p.oy / height - pointer.y;
      const distance = Math.max(0.001, Math.sqrt(dx * dx + dy * dy));
      const repel = pointer.active ? Math.max(0, 0.18 - distance) / 0.18 : 0;
      const wave = Math.sin(frame * 1.2 + p.phase + p.ox * 0.006) * 2.2;
      const drift = Math.sin(frame * 0.35 + p.phase) * 3;
      p.x = p.ox + dx * repel * 70 + drift;
      p.y = p.oy + dy * repel * 52 + wave;

      const flicker = 0.78 + Math.sin(frame * 2.8 + p.phase) * 0.22;
      ctx.globalAlpha = p.a * flicker;
      ctx.fillStyle = p.warm ? "#f4c430" : p.red ? "#e5312f" : p.cyan ? "#1aa7c8" : "#c7cbd1";
      ctx.fillRect(Math.round(p.x), Math.round(p.y), p.s, p.s);
    }

    ctx.globalAlpha = 1;
    if (!reduceMotion) animationFrameId = requestAnimationFrame(draw);
  };

  const start = () => {
    if (running || reduceMotion || !visible) return;
    running = true;
    animationFrameId = requestAnimationFrame(draw);
  };

  const stop = () => {
    running = false;
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
  };

  window.addEventListener("resize", build);
  window.addEventListener("lumasift:workflow", build);
  document.addEventListener("visibilitychange", () => {
    visible = document.visibilityState === "visible";
    if (visible) start();
    else stop();
  });
  window.addEventListener("pointermove", (event) => {
    pointer.x = (event.clientX - canvasRect.left) / canvasRect.width;
    pointer.y = (event.clientY - canvasRect.top) / canvasRect.height;
    pointer.active = true;
  });
  window.addEventListener("pointerleave", () => {
    pointer.active = false;
  });

  const observer = new IntersectionObserver(([entry]) => {
    visible = Boolean(entry?.isIntersecting);
    if (visible) start();
    else stop();
  }, { threshold: 0.05 });
  observer.observe(canvas);

  build();
  if (reduceMotion) {
    running = true;
    draw(0);
    running = false;
  } else {
    start();
  }
}

createParticleField(particleCanvas);
