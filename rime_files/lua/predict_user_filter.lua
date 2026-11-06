-- 用户自定义联想（由 Rime 词库工具维护 predict_user.tsv）
-- 文件格式：前词<Tab>联想词，同一前词按行序显示；前词<Tab>!联想词 表示隐藏词库里的这个词。
-- 词库有联想时：用户词排最前，并去掉隐藏词。词库没有该前词时：放一个联想段，只显示用户词。
local M = {}

local function load_table()
  local map = {}
  local f = io.open(rime_api.get_user_data_dir() .. "/predict_user.tsv", "r")
  if not f then return map end
  for line in f:lines() do
    line = line:gsub("\r$", "")
    if line ~= "" and line:sub(1, 1) ~= "#" then
      local head, word = line:match("^([^\t]+)\t([^\t]+)")
      if head and word then
        local e = map[head]
        if not e then e = { pins = {}, hidden = {} }; map[head] = e end
        if word:sub(1, 1) == "!" then
          e.hidden[word:sub(2)] = true
        else
          table.insert(e.pins, word)
        end
      end
    end
  end
  f:close()
  return map
end

local function entry_for(env, ctx)
  local text = ctx.commit_history:latest_text()
  if text == "" then return nil end
  return env.map[text]
end

function M.init(env)
  env.map = load_table()
  env.pending = false
  local ctx = env.engine.context
  env.c1 = ctx.commit_notifier:connect(function() env.pending = true end)
  env.c2 = ctx.update_notifier:connect(function(c)
    if not env.pending then return end
    env.pending = false
    if not c.composition:empty() then return end
    if not c:get_option("prediction") or c:get_option("ascii_mode") then return end
    local e = entry_for(env, c)
    if not e or #e.pins == 0 then return end
    local pos = #c.input
    local seg = Segment(pos, pos)
    seg.tags = Set({ "prediction", "placeholder" })
    local menu = Menu()
    menu:add_translation(Translation(function()
      for _, w in ipairs(e.pins) do
        yield(Candidate("prediction", pos, pos, w, ""))
      end
    end))
    seg.menu = menu
    c.composition:push_back(seg)
  end)
end

function M.fini(env)
  if env.c1 then env.c1:disconnect() end
  if env.c2 then env.c2:disconnect() end
end

function M.func(input, env)
  local first, seen, hidden = true, {}, {}
  for cand in input:iter() do
    if first then
      first = false
      if cand.type == "prediction" then
        local e = entry_for(env, env.engine.context)
        if e then
          hidden = e.hidden
          for _, w in ipairs(e.pins) do
            if not seen[w] then
              seen[w] = true
              yield(Candidate("prediction", cand.start, cand._end, w, ""))
            end
          end
        end
      end
    end
    if cand.type == "prediction" then
      if not seen[cand.text] and not hidden[cand.text] then yield(cand) end
    else
      yield(cand)
    end
  end
end

return M
