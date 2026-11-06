-- 联想状态下按句号：结束联想并输出句号，效果和逗号一样。
-- Rime 默认把句号绑定为“有候选时下一页”，联想候选也算候选，所以句号会被翻页吃掉。
-- 不能用 ctx:clear()：输入清空后 predictor 会马上重新联想，句号又被翻页吃掉。
-- 只处理联想状态，平时打字时句号翻页的行为不变。
local kAccepted, kNoop = 1, 2
local PERIOD = 0x2e

local function func(key, env)
  if key.keycode ~= PERIOD or key:release() or key:ctrl() or key:alt() then
    return kNoop
  end
  local ctx = env.engine.context
  local comp = ctx.composition
  if comp:empty() or not comp:back():has_tag("prediction") then
    return kNoop
  end
  ctx:push_input(".")
  ctx:commit()
  return kAccepted
end

return { func = func }
