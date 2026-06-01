import assert from "node:assert/strict";
import test from "node:test";
import { QWEN_STORY_PROMPT_VERSION, isCurrentConcreteQwenReview, validateQwenStoryData } from "../ts_core/qwenReview";
import { buildEditingAdvice } from "../ts_core/editingAdvice";
import { PhotoReviewRecord } from "../ts_core/types";

test("current concrete qwen review requires status, source, quality, and prompt version", () => {
  const record: PhotoReviewRecord = {
    analysis_source: "qwen_vision",
    analysis_quality: "concrete",
    qwen_status: "done",
    qwen_prompt_version: QWEN_STORY_PROMPT_VERSION
  };
  assert.equal(isCurrentConcreteQwenReview(record), true);
  assert.equal(isCurrentConcreteQwenReview({ ...record, qwen_prompt_version: "qwen-story-v8" }), false);
  assert.equal(isCurrentConcreteQwenReview({ ...record, analysis_quality: "weak" }), false);
});

test("template-like keyword review is rejected", () => {
  assert.throws(() =>
    validateQwenStoryData({
      editorial_verdict: { action: "keep", confidence: 78, one_line_reason: "前景人物和背景街道形成清晰关系，画面具有现场感" },
      visible_evidence: ["前景人物和背景街道形成关系", "左侧人物与右侧车辆形成层次", "画面边缘元素提供现场感", "主体和环境关系清晰"],
      subject_relationship: "前景人物和背景街道形成清晰主体关系",
      decisive_moment_read: "人物和车辆的瞬间关系较为完整"
    })
  );
});

test("overpraised review without critical flaws is rejected", () => {
  const data = balancedReview();
  data.critical_flaws = ["暂无明显风险", "轻微可修"];
  data.professional_review!.editorial_summary = "红色钢梁和上方人物形成非常成功的结构，画面优秀且非常完整，是强烈作品候选。";
  assert.throws(() => validateQwenStoryData(data), /critical flaws|praise-heavy/);
});

test("unsupported person and motion claim is rejected", () => {
  const data = balancedReview();
  data.visible_inventory = {
    main_subject: "红色钢梁和玻璃天窗",
    people: [],
    setting_context: ["工业建筑"],
    gesture_expression_motion: ["没有可读人物动作"]
  };
  data.visible_evidence![0] = "画面下方行人在黑色横梁旁行走，动作方向让工业空间更有故事";
  assert.throws(() => validateQwenStoryData(data), /unsupported person|human value/);
});

test("formal photo without readable person cannot be over-scored as human story", () => {
  const data = balancedReview();
  data.storytelling_score = 78;
  data.human_documentary_value_score = 76;
  data.decisive_moment_score = 72;
  data.category = "portfolio_candidate";
  data.editorial_verdict = { action: "keep", confidence: 82, one_line_reason: "红色钢梁和疑似人形形成强烈工业空间关系" };
  data.visible_inventory = {
    main_subject: "红色钢梁、玻璃天窗和金属网格",
    people: [{ id: "u1", region: "中部平台", visibility: "uncertain", pose_or_motion: "疑似人形但看不清", confidence: 35 }],
    setting_context: ["工业建筑"],
    gesture_expression_motion: ["看不清"]
  };
  assert.throws(() => validateQwenStoryData(data), /unsupported person|overstated story|human value/);
});

test("balanced concrete review is accepted", () => {
  validateQwenStoryData(balancedReview());
});

test("stale qwen edit plan is not reused", () => {
  const advice = buildEditingAdvice(
    {
      filename: "stale.jpg",
      analysis_source: "qwen_vision",
      analysis_quality: "concrete",
      qwen_status: "done",
      qwen_prompt_version: "qwen-story-v8",
      specific_edit_parameters: { contrast: "+99" },
      editing_plan: {
        edit_intent: "old qwen intent",
        crop_plan: { keep: ["old subject"], remove_or_reduce: ["old edge"] },
        local_masks: [{ target: "old", operation: "Exposure +1", reason: "old" }]
      }
    },
    "en"
  );
  assert.equal(advice.editing_advice_source, "technical_draft");
  assert.notEqual(advice.lightroom_parameters.contrast, "+99");
  assert.notDeepEqual(advice.crop_plan.keep, ["old subject"]);
});

test("rejected current qwen review does not produce Lightroom recipe", () => {
  const advice = buildEditingAdvice(
    {
      filename: "reject.jpg",
      category: "reject_candidate",
      analysis_source: "qwen_vision",
      analysis_quality: "concrete",
      qwen_status: "done",
      qwen_prompt_version: QWEN_STORY_PROMPT_VERSION,
      editorial_verdict: { action: "reject", confidence: 95, one_line_reason: "foreground head blocks the station sign and distant pedestrians" },
      visible_evidence: ["foreground head blocks the station sign", "green pillar splits the station background", "DB station sign remains readable"],
      subject_relationship: "Foreground head, station sign, and distant pedestrians do not form a usable relationship.",
      decisive_moment_read: "No readable gesture or timing survives the foreground obstruction."
    },
    "en"
  );
  assert.equal(advice.editing_advice_source, "rejected_by_vision");
  assert.deepEqual(advice.lightroom_parameters, {});
  assert.match(advice.crop_plan.reason, /cannot rescue/);
});

function balancedReview(): PhotoReviewRecord {
  return {
    analysis_source: "qwen_vision",
    analysis_quality: "concrete",
    qwen_status: "done",
    qwen_prompt_version: QWEN_STORY_PROMPT_VERSION,
    category: "ordinary_record",
    editorial_verdict: {
      action: "maybe",
      confidence: 64,
      one_line_reason: "画面上方站立人物被红色钢梁和网格包围，但面部不可读使人文判断受限"
    },
    professional_review: {
      editorial_summary: "红色钢梁和玻璃天窗给画面上方站立人物制造压迫结构，但人物面部不可读，作品性主要来自形式而非情节。",
      story_read: "上方人物确实提供尺度参照，金属网格让空间更疏离；限制是没有表情和视线，故事只能停在环境观察。",
      composition_read: "左侧红色斜梁能把视线带到上方人物，底部黑色横梁也压住画面；但网格过密会削弱人物可读性。",
      selection_logic: "这帧可作为待定结构片保留比较，若相邻帧人物姿态或面部更清楚，应优先换掉这一帧。",
      editing_logic: "后期可压高光并微提上方人物轮廓，但不能补出表情、视线或明确动作关系。"
    },
    visible_inventory: {
      main_subject: "上方站立人物和红色钢梁",
      people: [{ id: "p1", region: "画面上方偏右", visibility: "clear", pose_or_motion: "站立但面部不可读", confidence: 82 }],
      setting_context: ["红色钢梁", "玻璃天窗", "金属网格"],
      gesture_expression_motion: ["站立", "表情看不清"]
    },
    visible_evidence: [
      "画面上方偏右的站立人物被红色钢梁包围，人物可见但面部不可读，因此故事分不能过高",
      "左侧红色斜梁从下往上切入画面，引导视线但也比人物更抢眼，选择上形成减分",
      "玻璃天窗大面积偏亮并压在人物背后，提供工业空间语境同时削弱轮廓细节",
      "金属网格覆盖人物和背景，制造疏离感但也让动作与表情更难读"
    ],
    subject_relationship: "上方人物和红色钢梁形成尺度关系，但人物情绪与动作不可读",
    decisive_moment_read: "瞬间偏弱，站立姿态没有明确动作峰值或视线关系",
    moment_status: "weak",
    storytelling_score: 62,
    human_documentary_value_score: 58,
    decisive_moment_score: 45,
    critical_flaws: [
      "上方人物面部不可读，无法靠修图补出表情或视线",
      "红色钢梁比人物更抢眼，形式结构压过人文内容"
    ],
    hallucination_checks: {
      unsupported_claims: [],
      uncertain_objects: ["中部平台暗部细节看不清"],
      spatial_sanity_check: "可确认人物在上方偏右，没有确认画面下方行人"
    },
    selection_risk: "人物情绪不可读，最终可能只是工业结构记录",
    edit_vs_select_warning: "修图能整理钢梁和天窗，不能补出决定性瞬间",
    frame_failure_reasons: ["人物面部不可读", "形式结构压过人文内容"],
    why_deprioritize: ["缺少表情、视线和明确动作关系"]
  };
}
