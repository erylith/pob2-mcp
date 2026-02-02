-- Path of Building API Bridge
-- Runs as: cd src && LUA_PATH="../runtime/lua/?.lua;../runtime/lua/?/init.lua;;" luajit ../api/lua/bridge.lua
-- Communicates via JSON-line protocol over stdin/stdout
-- stderr is used for logging (ConPrintf redirected there)

-- ============================================================================
-- Phase 1: Bootstrap
-- ============================================================================

-- Redirect ConPrintf and print to stderr to keep stdout clean for JSON protocol
function ConPrintf(fmt, ...)
	io.stderr:write(string.format(fmt, ...) .. "\n")
	io.stderr:flush()
end
local _orig_print = print
function print(...)
	local args = {...}
	local parts = {}
	for i = 1, select("#", ...) do
		parts[i] = tostring(args[i])
	end
	io.stderr:write(table.concat(parts, "\t") .. "\n")
	io.stderr:flush()
end

-- Load the rest of HeadlessWrapper's stubs and globals
-- We replicate the essential parts here since we override ConPrintf

-- Callbacks
local callbackTable = { }
local mainObject
function runCallback(name, ...)
	if callbackTable[name] then
		return callbackTable[name](...)
	elseif mainObject and mainObject[name] then
		return mainObject[name](mainObject, ...)
	end
end
function SetCallback(name, func)
	callbackTable[name] = func
end
function GetCallback(name)
	return callbackTable[name]
end
function SetMainObject(obj)
	mainObject = obj
end

-- Image Handles
local imageHandleClass = { }
imageHandleClass.__index = imageHandleClass
function NewImageHandle()
	return setmetatable({ }, imageHandleClass)
end
function imageHandleClass:Load(fileName, ...) self.valid = true end
function imageHandleClass:Unload() self.valid = false end
function imageHandleClass:IsValid() return self.valid end
function imageHandleClass:SetLoadingPriority(pri) end
function imageHandleClass:ImageSize() return 1, 1 end

-- Rendering
function RenderInit(flag, ...) end
function GetScreenSize() return 1920, 1080 end
function GetScreenScale() return 1 end
function GetDPIScaleOverridePercent() return 1 end
function SetDPIScaleOverridePercent(scale) end
function SetClearColor(r, g, b, a) end
function SetDrawLayer(layer, subLayer) end
function SetViewport(x, y, width, height) end
function SetDrawColor(r, g, b, a) end
function GetDrawColor(r, g, b, a) end
function DrawImage(imgHandle, left, top, width, height, tcLeft, tcTop, tcRight, tcBottom) end
function DrawImageQuad(imageHandle, x1, y1, x2, y2, x3, y3, x4, y4, s1, t1, s2, t2, s3, t3, s4, t4) end
function DrawString(left, top, align, height, font, text) end
function DrawStringWidth(height, font, text) return 1 end
function DrawStringCursorIndex(height, font, text, cursorX, cursorY) return 0 end
function StripEscapes(text)
	return text:gsub("%^%d",""):gsub("%^x%x%x%x%x%x%x","")
end
function GetAsyncCount() return 0 end

-- Search Handles
local isWindows = package.config:sub(1,1) == "\\"

function NewFileSearch(pattern, isDirSearch)
	local dir = pattern:match("^(.*[/\\])") or "./"
	local glob = pattern:match("[^/\\]+$") or "*"
	-- Convert glob pattern to Lua pattern
	local luaPat = "^" .. glob:gsub("[%.%-%+%[%]%(%)%$%^%%]", "%%%0"):gsub("%*", ".*"):gsub("%?", ".") .. "$"

	local entries = {}
	local cmd
	if isWindows then
		cmd = 'dir /b "' .. dir .. '" 2>NUL'
	else
		cmd = 'ls -1 "' .. dir .. '" 2>/dev/null'
	end
	local pipe = io.popen(cmd)
	if pipe then
		for name in pipe:lines() do
			if name:match(luaPat) then
				local fullPath = dir .. name
				-- Check if entry is a directory
				local entryIsDir = false
				if isWindows then
					local dp = io.popen('if exist "' .. fullPath .. '\\*" (echo DIR) else (echo FILE)')
					if dp then
						local res = dp:read("*l")
						dp:close()
						entryIsDir = (res == "DIR")
					end
				else
					local dp = io.popen('test -d "' .. fullPath .. '" && echo DIR || echo FILE')
					if dp then
						local res = dp:read("*l")
						dp:close()
						entryIsDir = (res == "DIR")
					end
				end
				if (isDirSearch and entryIsDir) or (not isDirSearch and not entryIsDir) then
					-- Get modification time
					local mtime = 0
					if not isWindows then
						local sp = io.popen('stat -f "%m" "' .. fullPath .. '" 2>/dev/null || stat -c "%Y" "' .. fullPath .. '" 2>/dev/null')
						if sp then
							local ts = sp:read("*l")
							sp:close()
							mtime = tonumber(ts) or 0
						end
					end
					table.insert(entries, { name = name, path = fullPath, mtime = mtime })
				end
			end
		end
		pipe:close()
	end

	if #entries == 0 then return nil end

	local idx = 1
	return {
		GetFileName = function(self) return entries[idx].name end,
		GetFileModifiedTime = function(self) return entries[idx].mtime end,
		NextFile = function(self)
			idx = idx + 1
			return idx <= #entries
		end,
	}
end

-- General Functions
function SetWindowTitle(title) end
function GetCursorPos() return 0, 0 end
function SetCursorPos(x, y) end
function ShowCursor(doShow) end
function IsKeyDown(keyName) end
function Copy(text) end
function Paste() end
function Deflate(data) return "" end
function Inflate(data) return "" end
function GetTime() return 0 end
function GetScriptPath() return "" end
function GetRuntimePath() return "" end
function GetUserPath() return "" end
function MakeDir(path)
	if isWindows then
		os.execute('mkdir "' .. path .. '" 2>NUL')
	else
		os.execute('mkdir -p "' .. path .. '" 2>/dev/null')
	end
end
function RemoveDir(path)
	os.remove(path)
end
function SetWorkDir(path) end
function GetWorkDir() return "" end
function LaunchSubScript(scriptText, funcList, subList, ...) end
function AbortSubScript(ssID) end
function IsSubScriptRunning(ssID) end
function LoadModule(fileName, ...)
	if not fileName:match("%.lua") then
		fileName = fileName .. ".lua"
	end
	local func, err = loadfile(fileName)
	if func then
		return func(...)
	else
		error("LoadModule() error loading '"..fileName.."': "..err)
	end
end
function PLoadModule(fileName, ...)
	if not fileName:match("%.lua") then
		fileName = fileName .. ".lua"
	end
	local func, err = loadfile(fileName)
	if func then
		return PCall(func, ...)
	else
		error("PLoadModule() error loading '"..fileName.."': "..err)
	end
end
function PCall(func, ...)
	local ret = { pcall(func, ...) }
	if ret[1] then
		table.remove(ret, 1)
		return nil, unpack(ret)
	else
		return ret[2]
	end
end
function ConPrintTable(tbl, noRecurse) end
function ConExecute(cmd) end
function ConClear() end
function SpawnProcess(cmdName, args) end
function OpenURL(url) end
function SetProfiling(isEnabled) end
function Restart() end
function Exit() end
function TakeScreenshot() end

function GetCloudProvider(fullPath)
	return nil, nil, nil
end

-- lua-utf8: try to load the real native C module first (available on Windows
-- via runtime/lua-utf8.dll when LUA_CPATH is set). If that fails, register a
-- fallback using standard string functions. The fallback covers all headless
-- usage (number formatting, cursor movement) but without true UTF-8 awareness.
local _utf8_ok, _utf8_mod = pcall(require, 'lua-utf8')
if not _utf8_ok then
	local utf8_fallback = {}
	utf8_fallback.byte    = string.byte
	utf8_fallback.char    = string.char
	utf8_fallback.find    = string.find
	utf8_fallback.gmatch  = string.gmatch
	utf8_fallback.gsub    = string.gsub
	utf8_fallback.len     = string.len
	utf8_fallback.lower   = string.lower
	utf8_fallback.match   = string.match
	utf8_fallback.rep     = string.rep
	utf8_fallback.reverse = string.reverse
	utf8_fallback.sub     = string.sub
	utf8_fallback.upper   = string.upper
	utf8_fallback.format  = string.format
	function utf8_fallback.next(s, idx, offset)
		if not offset then offset = 1 end
		if offset > 0 then
			local pos = idx
			for _ = 1, offset do
				if pos > #s then return nil end
				pos = pos + 1
			end
			return pos
		else
			local pos = idx
			for _ = 1, -offset do
				if pos <= 1 then return nil end
				pos = pos - 1
			end
			return pos
		end
	end
	package.preload['lua-utf8'] = function() return utf8_fallback end
	ConPrintf("Bridge: Using lua-utf8 fallback (native module not available)")
else
	ConPrintf("Bridge: Using native lua-utf8 module")
end

local l_require = require
function require(name)
	if name == "lcurl.safe" then
		return
	end
	return l_require(name)
end

-- ============================================================================
-- Load the application
-- ============================================================================

ConPrintf("Bridge: Loading Launch.lua...")
dofile("Launch.lua")

mainObject.continuousIntegrationMode = os.getenv("CI")

ConPrintf("Bridge: Running OnInit...")
runCallback("OnInit")
ConPrintf("Bridge: Running initial OnFrame...")
runCallback("OnFrame")

if mainObject.promptMsg then
	io.stderr:write("Bridge startup error: " .. tostring(mainObject.promptMsg) .. "\n")
	io.stderr:flush()
	os.exit(1)
end

build = mainObject.main.modes["BUILD"]

-- ============================================================================
-- Builds path auto-detection
-- ============================================================================

local function readBuildPathFromSettings(userPath)
	local f = io.open(userPath .. "Settings.xml", "r")
	if not f then return nil end
	local content = f:read("*a")
	f:close()
	local buildPath = content:match('buildPath="([^"]+)"')
	return buildPath
end

local function detectBuildsPath()
	-- 1. Explicit override via env var always wins
	local envPath = os.getenv("POB_BUILDS_PATH")
	if envPath and envPath ~= "" then return envPath end

	-- 2. Auto-detect the GUI's default directory
	local candidates = {}
	local userPaths = {}

	if isWindows then
		local userProfile = os.getenv("USERPROFILE") or ""
		local base = userProfile .. "\\Documents\\Path of Building (PoE2)\\"
		table.insert(userPaths, base)
		table.insert(candidates, base .. "Builds\\")
		local oneDrive = os.getenv("OneDrive") or os.getenv("OneDriveConsumer") or ""
		if oneDrive ~= "" then
			local odBase = oneDrive .. "\\Documents\\Path of Building (PoE2)\\"
			table.insert(userPaths, odBase)
			table.insert(candidates, odBase .. "Builds\\")
		end
	else
		local home = os.getenv("HOME") or ""
		local base1 = home .. "/Documents/Path of Building (PoE2)/"
		local base2 = home .. "/Path of Building (PoE2)/"
		table.insert(userPaths, base1)
		table.insert(userPaths, base2)
		table.insert(candidates, base1 .. "Builds/")
		table.insert(candidates, base2 .. "Builds/")
	end

	-- 3. Check Settings.xml for a custom buildPath override
	for _, userPath in ipairs(userPaths) do
		local customPath = readBuildPathFromSettings(userPath)
		if customPath and customPath ~= "" then
			-- Ensure trailing separator
			local sep = isWindows and "\\" or "/"
			if customPath:sub(-1) ~= "/" and customPath:sub(-1) ~= "\\" then
				customPath = customPath .. sep
			end
			-- Verify the directory is listable
			local testCmd = isWindows
				and ('dir /b "' .. customPath .. '" 2>NUL')
				or ('ls "' .. customPath .. '" 2>/dev/null')
			local pipe = io.popen(testCmd)
			if pipe then
				local firstLine = pipe:read("*l")
				pipe:close()
				if firstLine ~= nil then
					return customPath
				end
			end
		end
	end

	-- 4. Check standard candidate directories
	for _, candidate in ipairs(candidates) do
		local testCmd = isWindows
			and ('dir /b "' .. candidate .. '" 2>NUL')
			or ('ls "' .. candidate .. '" 2>/dev/null')
		local pipe = io.popen(testCmd)
		if pipe then
			local firstLine = pipe:read("*l")
			pipe:close()
			if firstLine ~= nil then
				return candidate
			end
		end
	end

	-- 5. Fallback: repo-relative Builds/ directory
	return "../Builds/"
end

local buildsPath = detectBuildsPath()
-- Ensure trailing separator
local sep = isWindows and "\\" or "/"
if buildsPath:sub(-1) ~= "/" and buildsPath:sub(-1) ~= "\\" then
	buildsPath = buildsPath .. sep
end

-- Convert to absolute path for consistency
local function getAbsolutePath(path)
	-- If already absolute, return as-is
	if isWindows then
		if path:match("^[A-Za-z]:") then return path end
	else
		if path:sub(1, 1) == "/" then return path end
	end
	
	-- Get current working directory
	local cwd = io.popen(isWindows and "cd" or "pwd"):read("*l")
	if cwd then
		return cwd .. sep .. path
	end
	return path
end

local function normalizePath(path)
	-- Normalize path separators to forward slashes
	path = path:gsub("\\", "/")
	
	-- Resolve . and .. components
	local components = {}
	for component in path:gmatch("[^/]+") do
		if component == ".." then
			-- Go up one directory
			if #components > 0 and components[#components] ~= ".." then
				table.remove(components)
			end
		elseif component ~= "." then
			-- Add normal component (skip .)
			table.insert(components, component)
		end
	end
	
	-- Check if original path was absolute
	local isAbsolute = path:sub(1, 1) == "/"
	if isWindows then
		isAbsolute = path:match("^[A-Za-z]:")
	end
	
	-- Reconstruct path
	local result = table.concat(components, "/")
	if isAbsolute then
		if isWindows then
			-- For Windows, we need to preserve the drive letter
			local drive = path:match("^([A-Za-z]:")
			if drive then
				result = drive .. "/" .. result
			else
				result = "/" .. result
			end
		else
			result = "/" .. result
		end
	end
	
	return result
end

buildsPath = normalizePath(getAbsolutePath(buildsPath))

-- Ensure trailing separator after absolute conversion
if buildsPath:sub(-1) ~= "/" and buildsPath:sub(-1) ~= "\\" then
	buildsPath = buildsPath .. sep
end

MakeDir(buildsPath)

-- Safety check: ensure mainObject.main exists
if not mainObject then
	error("mainObject not initialized - bridge startup failed")
end
if not mainObject.main then
	error("mainObject.main not initialized - bridge startup failed")
end

mainObject.main.buildPath = buildsPath
mainObject.main.defaultBuildPath = buildsPath
ConPrintf("Bridge: Builds path: %s", buildsPath)

-- Helper functions from HeadlessWrapper
function newBuild()
	mainObject.main:SetMode("BUILD", false, "Help, I'm stuck in Path of Building!")
	runCallback("OnFrame")
	build = mainObject.main.modes["BUILD"]
end

function loadBuildFromXML(xmlText, name)
	mainObject.main:SetMode("BUILD", false, name or "", xmlText)
	runCallback("OnFrame")
	build = mainObject.main.modes["BUILD"]
end

-- ============================================================================
-- Load JSON library
-- ============================================================================

local dkjson = LoadModule("../runtime/lua/dkjson.lua")

-- ============================================================================
-- JSON serialization helpers
-- ============================================================================

local MAX_DEPTH = 5

local function safeSerialize(val, depth)
	if depth > MAX_DEPTH then
		return nil
	end
	local t = type(val)
	if t == "nil" or t == "boolean" or t == "number" then
		return val
	elseif t == "string" then
		return val
	elseif t == "table" then
		-- Check if it's an array-like table
		local isArray = true
		local maxN = 0
		local count = 0
		for k, _ in pairs(val) do
			count = count + 1
			if type(k) == "number" and k == math.floor(k) and k > 0 then
				if k > maxN then maxN = k end
			else
				isArray = false
			end
		end
		if count == 0 then
			return {}
		end
		-- If it has numeric keys and count matches, treat as array
		if isArray and maxN == count then
			local arr = {}
			for i = 1, maxN do
				arr[i] = safeSerialize(val[i], depth + 1)
			end
			return arr
		end
		-- Otherwise, treat as object
		local obj = {}
		for k, v in pairs(val) do
			if type(k) == "string" or type(k) == "number" then
				local sv = safeSerialize(v, depth + 1)
				if sv ~= nil then
					obj[tostring(k)] = sv
				end
			end
		end
		return obj
	else
		-- Skip functions, userdata, threads
		return nil
	end
end

local function jsonEncode(val)
	local safe = safeSerialize(val, 0)
	return dkjson.encode(safe)
end

local function jsonDecode(str)
	return dkjson.decode(str)
end

-- ============================================================================
-- Response helpers
-- ============================================================================

local function respond(result)
	local json = dkjson.encode({ ok = true, result = result })
	io.stdout:write(json .. "\n")
	io.stdout:flush()
end

local function respondError(msg)
	local json = dkjson.encode({ ok = false, error = tostring(msg) })
	io.stdout:write(json .. "\n")
	io.stdout:flush()
end

-- ============================================================================
-- Recalculation helper
-- ============================================================================

local function recalc()
	build.buildFlag = true
	runCallback("OnFrame")
end

-- ============================================================================
-- Curated stats for get_output
-- ============================================================================

local CURATED_STATS = {
	"TotalDPS", "CombinedDPS", "FullDPS", "TotalDot", "AverageHit",
	"AverageDamage", "Speed", "CritChance", "CritMultiplier", "HitChance",
	"BleedDPS", "IgniteDPS", "PoisonDPS", "DecayDPS", "TotalDotDPS",
	"ImpaleDPS", "WithBleedDPS", "WithIgniteDPS", "WithPoisonDPS",
	"WithImpaleDPS", "MirageDPS", "CullingDPS", "CombinedAvg",
	"Life", "LifeUnreserved", "LifeRegenRecovery", "LifeLeechGainRate",
	"Mana", "ManaUnreserved", "ManaRegenRecovery", "ManaLeechGainRate",
	"EnergyShield", "EnergyShieldRegenRecovery", "EnergyShieldLeechGainRate",
	"Spirit", "SpiritUnreserved",
	"Str", "Dex", "Int",
	"TotalEHP",
	"PhysicalMaximumHitTaken", "FireMaximumHitTaken",
	"ColdMaximumHitTaken", "LightningMaximumHitTaken", "ChaosMaximumHitTaken",
	"Evasion", "EvadeChance", "Armour", "PhysicalDamageReduction",
	"EffectiveBlockChance", "EffectiveSpellBlockChance",
	"AttackDodgeChance", "SpellDodgeChance",
	"EffectiveSpellSuppressionChance",
	"FireResist", "ColdResist", "LightningResist", "ChaosResist",
	"FireResistOverCap", "ColdResistOverCap", "LightningResistOverCap", "ChaosResistOverCap",
	"EffectiveMovementSpeedMod",
	"ManaCost", "LifeCost",
	"NetLifeRegen", "NetManaRegen", "NetEnergyShieldRegen",
	"TotalNetRegen", "TotalBuildDegen",
	"Rage", "RageRegenRecovery",
	"Devotion", "Tribute",
}

-- ============================================================================
-- Path validation helper
-- ============================================================================

local function validateBuildPath(path, operation)
	-- Validate path is within builds path for security
	local buildsPath = mainObject.main.buildPath
	if not buildsPath then
		error("Builds path not configured - bridge initialization incomplete")
	end
	
	-- Convert path to absolute for consistent validation
	local absPath = path
	if not isWindows then
		if path:sub(1, 1) ~= "/" then
			-- Relative path, convert to absolute
			local cwd = io.popen("pwd"):read("*l")
			if cwd then
				absPath = cwd .. "/" .. path
			end
		end
	else
		-- Windows: check if path starts with drive letter
		if not path:match("^[A-Za-z]:") then
			local cwd = io.popen("cd"):read("*l")
			if cwd then
				absPath = cwd .. "\\" .. path
			end
		end
	end
	
	-- Normalize both paths (resolve . and .. components)
	local normalizedPath = normalizePath(absPath)
	local normalizedBuildsPath = normalizePath(buildsPath)
	
	-- Ensure buildsPath ends with separator for proper prefix matching
	if normalizedBuildsPath:sub(-1) ~= "/" then
		normalizedBuildsPath = normalizedBuildsPath .. "/"
	end
	
	-- Check if normalized path starts with normalized buildsPath
	if not normalizedPath:find("^" .. normalizedBuildsPath:gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0")) then
		error("Path must be within builds directory: " .. path .. " (builds path: " .. buildsPath .. ")")
	end
	
	-- Additional check: ensure the normalized path doesn't escape via .. after normalization
	if normalizedPath:find("%.%./") then
		error("Path contains invalid traversal sequence: " .. path)
	end
	
	return normalizedPath
end

-- ============================================================================
-- Command dispatch table
-- ============================================================================

local commands = {}

function commands.ping(params)
	return { pong = true }
end

function commands.new_build(params)
	newBuild()
	return { success = true }
end

function commands.load_build_xml(params)
	if not params.xml then
		error("Missing 'xml' parameter")
	end
	loadBuildFromXML(params.xml, params.name)
	return { success = true }
end

function commands.get_build_info(params)
	if not build then
		error("No build loaded")
	end
	local info = {
		className = build.spec and build.spec.curClassName or nil,
		ascendClassName = build.spec and build.spec.curAscendClassName or nil,
		level = build.characterLevel,
		mainSocketGroup = build.mainSocketGroup,
		viewMode = build.viewMode,
		buildName = build.buildName,
	}
	return info
end

function commands.get_build_xml(params)
	if not build then
		error("No build loaded")
	end
	local xmlText = build:SaveDB("export")
	return { xml = xmlText }
end

function commands.alloc_node(params)
	if not build or not build.spec then
		error("No build loaded")
	end
	local nodeId = tonumber(params.node_id)
	if not nodeId then
		error("Missing or invalid 'node_id' parameter")
	end
	local node = build.spec.nodes[nodeId]
	if not node then
		error("Node " .. nodeId .. " not found")
	end
	if node.alloc then
		return { success = true, already_allocated = true }
	end
	build.spec:AllocNode(node)
	recalc()
	return { success = true }
end

function commands.dealloc_node(params)
	if not build or not build.spec then
		error("No build loaded")
	end
	local nodeId = tonumber(params.node_id)
	if not nodeId then
		error("Missing or invalid 'node_id' parameter")
	end
	local node = build.spec.allocNodes[nodeId]
	if not node then
		-- Check if the node exists but isn't allocated
		if build.spec.nodes[nodeId] then
			return { success = true, already_deallocated = true }
		end
		error("Node " .. nodeId .. " not found")
	end
	build.spec:DeallocNode(node)
	recalc()
	return { success = true }
end

function commands.list_alloc_nodes(params)
	if not build or not build.spec then
		error("No build loaded")
	end
	local nodes = {}
	for id, node in pairs(build.spec.allocNodes) do
		table.insert(nodes, {
			id = id,
			name = node.dn or node.name,
			type = node.type,
			ascendancyName = node.ascendancyName,
		})
	end
	return { nodes = nodes }
end

function commands.search_nodes(params)
	if not build or not build.spec then
		error("No build loaded")
	end
	local query = (params.query or ""):lower()
	if query == "" then
		error("Missing 'query' parameter")
	end
	local results = {}
	local count = 0
	local maxResults = params.max_results or 50
	for id, node in pairs(build.spec.nodes) do
		if node.dn and node.dn:lower():find(query, 1, true) then
			table.insert(results, {
				id = id,
				name = node.dn,
				type = node.type,
				alloc = node.alloc or false,
				ascendancyName = node.ascendancyName,
			})
			count = count + 1
			if count >= maxResults then
				break
			end
		end
	end
	return { nodes = results, count = count }
end

function commands.get_node_info(params)
	if not build or not build.spec then
		error("No build loaded")
	end
	local nodeId = tonumber(params.node_id)
	if not nodeId then
		error("Missing or invalid 'node_id' parameter")
	end
	local node = build.spec.nodes[nodeId]
	if not node then
		error("Node " .. nodeId .. " not found")
	end
	local mods = {}
	if node.sd then
		for _, line in ipairs(node.sd) do
			table.insert(mods, line)
		end
	end
	local linkedIds = {}
	if node.linked then
		for _, linked in ipairs(node.linked) do
			table.insert(linkedIds, linked.id)
		end
	end
	return {
		id = nodeId,
		name = node.dn or node.name,
		type = node.type,
		alloc = node.alloc or false,
		ascendancyName = node.ascendancyName,
		mods = mods,
		linked = linkedIds,
		classStartIndex = node.classStartIndex,
		isMultipleChoice = node.isMultipleChoice or false,
		isMultipleChoiceOption = node.isMultipleChoiceOption or false,
		passivePointsGranted = node.passivePointsGranted or 0,
	}
end

function commands.list_items(params)
	if not build or not build.itemsTab then
		error("No build loaded")
	end
	local items = {}
	for id, item in pairs(build.itemsTab.items) do
		table.insert(items, {
			id = id,
			name = item.name or "Unknown",
			baseName = item.baseName,
			type = item.type,
			rarity = item.rarity,
		})
	end
	return { items = items }
end

function commands.get_item_details(params)
	if not build or not build.itemsTab then
		error("No build loaded")
	end
	
	local itemId = tonumber(params.item_id)
	if not itemId then
		error("Missing or invalid 'item_id' parameter")
	end
	
	local item = build.itemsTab.items[itemId]
	if not item then
		error("Item " .. itemId .. " not found")
	end
	
	-- Build result with all available item data
	local result = {
		id = itemId,
		name = item.name,
		baseName = item.baseName,
		type = item.type,
		subType = item.base and item.base.subType or nil,
		rarity = item.rarity,
		quality = item.quality,
		itemLevel = item.itemLevel,
		corrupted = item.corrupted or false,
		mirrored = item.mirrored or false,
		socketLimit = item.base and item.base.socketLimit or nil,
	}
	
	-- Add base stats
	if item.base then
		result.base = {
			type = item.base.type,
			subType = item.base.subType,
			socketLimit = item.base.socketLimit,
			quality = item.base.quality,
		}
		
		-- Add weapon data if applicable
		if item.base.weapon then
			result.base.weapon = item.base.weapon
		end
		
		-- Add armour data if applicable
		if item.base.armour then
			result.base.armour = item.base.armour
		end
	end
	
	-- Add requirements
	if item.requirements then
		result.requirements = item.requirements
	end
	
	-- Add mods
	local function formatModLines(modLines)
		local lines = {}
		for _, modLine in ipairs(modLines) do
			if modLine.line then
				table.insert(lines, modLine.line)
			end
		end
		return lines
	end
	
	result.implicits = formatModLines(item.implicitModLines or {})
	result.explicits = formatModLines(item.explicitModLines or {})
	result.enchants = formatModLines(item.enchantModLines or {})
	result.runes = formatModLines(item.runeModLines or {})
	
	-- Add equipped slot info
	for slotName, slot in pairs(build.itemsTab.slots) do
		if slot.selItemId == itemId then
			result.equippedSlot = slotName
			break
		end
	end
	
	return result
end

function commands.list_slots(params)
	if not build or not build.itemsTab then
		error("No build loaded")
	end
	local slots = {}
	for _, slot in ipairs(build.itemsTab.orderedSlots) do
		local itemId = slot.selItemId or 0
		local itemName = nil
		if itemId > 0 and build.itemsTab.items[itemId] then
			itemName = build.itemsTab.items[itemId].name
		end
		table.insert(slots, {
			slotName = slot.slotName,
			itemId = itemId,
			itemName = itemName,
		})
	end
	return { slots = slots }
end

function commands.add_item(params)
	if not build or not build.itemsTab then
		error("No build loaded")
	end
	local itemRaw = params.item_raw
	if not itemRaw then
		error("Missing 'item_raw' parameter")
	end
	local item = new("Item", itemRaw)
	if not item.base then
		error("Failed to parse item: unrecognized base type")
	end
	item:BuildModList()
	build.itemsTab:AddItem(item, params.slot == nil)
	build.itemsTab:PopulateSlots()
	build.itemsTab:AddUndoState()
	-- Optionally equip to a specific slot
	if params.slot then
		local slot = build.itemsTab.slots[params.slot]
		if slot then
			slot:SetSelItemId(item.id)
			build.itemsTab:PopulateSlots()
		end
	end
	recalc()
	return { success = true, item_id = item.id }
end

function commands.equip_item(params)
	if not build or not build.itemsTab then
		error("No build loaded")
	end
	local itemId = tonumber(params.item_id)
	if not itemId then
		error("Missing or invalid 'item_id' parameter")
	end
	if not build.itemsTab.items[itemId] then
		error("Item " .. itemId .. " not found")
	end
	local slotName = params.slot
	if not slotName then
		error("Missing 'slot' parameter")
	end
	local slot = build.itemsTab.slots[slotName]
	if not slot then
		error("Slot '" .. slotName .. "' not found")
	end
	slot:SetSelItemId(itemId)
	build.itemsTab:PopulateSlots()
	recalc()
	return { success = true }
end

function commands.unequip_slot(params)
	if not build or not build.itemsTab then
		error("No build loaded")
	end
	local slotName = params.slot
	if not slotName then
		error("Missing 'slot' parameter")
	end
	local slot = build.itemsTab.slots[slotName]
	if not slot then
		error("Slot '" .. slotName .. "' not found")
	end
	slot:SetSelItemId(0)
	build.itemsTab:PopulateSlots()
	recalc()
	return { success = true }
end

function commands.delete_item(params)
	if not build or not build.itemsTab then
		error("No build loaded")
	end
	local itemId = tonumber(params.item_id)
	if not itemId then
		error("Missing or invalid 'item_id' parameter")
	end
	local item = build.itemsTab.items[itemId]
	if not item then
		error("Item " .. itemId .. " not found")
	end
	build.itemsTab:DeleteItem(item)
	recalc()
	return { success = true }
end

function commands.list_skills(params)
	if not build or not build.skillsTab then
		error("No build loaded")
	end
	local skills = {}
	for i, group in ipairs(build.skillsTab.socketGroupList) do
		local gems = {}
		for _, gem in ipairs(group.gemList) do
			table.insert(gems, {
				nameSpec = gem.nameSpec,
				level = gem.level,
				quality = gem.quality,
				enabled = gem.enabled,
				count = gem.count,
				skillId = gem.skillId,
				gemId = gem.gemId,
			})
		end
		table.insert(skills, {
			index = i,
			label = group.label,
			enabled = group.enabled,
			slot = group.slot,
			source = group.source,
			mainActiveSkill = group.mainActiveSkill,
			isMainGroup = (i == build.mainSocketGroup),
			gems = gems,
		})
	end
	return { skills = skills }
end

function commands.add_skill(params)
	if not build or not build.skillsTab then
		error("No build loaded")
	end
	local skillText = params.skill_text
	if not skillText then
		error("Missing 'skill_text' parameter")
	end
	-- Parse the skill text similar to PasteSocketGroup
	local newGroup = { label = "", enabled = true, gemList = {} }
	local label = skillText:match("Label: (%C+)")
	if label then newGroup.label = label end
	local slot = skillText:match("Slot: (%C+)")
	if slot then newGroup.slot = slot end
	for nameSpec, level, quality, state, count in
		skillText:gmatch("([ %a']+) (%d+)/(%d+) ?(%a*) ?(%d*)") do
		table.insert(newGroup.gemList, {
			nameSpec = nameSpec:match("^%s*(.-)%s*$"), -- trim
			level = tonumber(level) or 20,
			quality = tonumber(quality) or 0,
			enabled = state ~= "DISABLED",
			count = tonumber(count) or 1,
			enableGlobal1 = true,
			enableGlobal2 = true,
		})
	end
	if #newGroup.gemList == 0 then
		error("No gems found in skill text. Expected format: 'GemName level/quality [count]'")
	end
	table.insert(build.skillsTab.socketGroupList, newGroup)
	build.skillsTab:AddUndoState()
	recalc()
	return {
		success = true,
		index = #build.skillsTab.socketGroupList,
		gem_count = #newGroup.gemList,
	}
end

function commands.remove_skill(params)
	if not build or not build.skillsTab then
		error("No build loaded")
	end
	local index = tonumber(params.index)
	if not index then
		error("Missing or invalid 'index' parameter")
	end
	if index < 1 or index > #build.skillsTab.socketGroupList then
		error("Index " .. index .. " out of range (1-" .. #build.skillsTab.socketGroupList .. ")")
	end
	local group = build.skillsTab.socketGroupList[index]
	if group.source then
		error("Cannot remove item-sourced skill group")
	end
	table.remove(build.skillsTab.socketGroupList, index)
	if build.mainSocketGroup > index then
		build.mainSocketGroup = build.mainSocketGroup - 1
	elseif build.mainSocketGroup > #build.skillsTab.socketGroupList then
		build.mainSocketGroup = math.max(1, #build.skillsTab.socketGroupList)
	end
	build.skillsTab:AddUndoState()
	recalc()
	return { success = true }
end

function commands.set_main_skill(params)
	if not build or not build.skillsTab then
		error("No build loaded")
	end
	local index = tonumber(params.index)
	if not index then
		error("Missing or invalid 'index' parameter")
	end
	if index < 1 or index > #build.skillsTab.socketGroupList then
		error("Index " .. index .. " out of range (1-" .. #build.skillsTab.socketGroupList .. ")")
	end
	build.mainSocketGroup = index
	recalc()
	return { success = true }
end

function commands.get_output(params)
	if not build or not build.calcsTab then
		error("No build loaded")
	end
	local output = build.calcsTab.mainOutput
	if not output then
		error("No calculation output available")
	end
	local result = {}
	local requestedStats = params.stats or CURATED_STATS
	for _, key in ipairs(requestedStats) do
		local val = output[key]
		if val ~= nil then
			if type(val) == "number" or type(val) == "string" or type(val) == "boolean" then
				result[key] = val
			end
		end
	end
	-- Include SkillDPS if available
	if output.SkillDPS and type(output.SkillDPS) == "table" then
		local skillDPS = {}
		for skillName, dpsVal in pairs(output.SkillDPS) do
			if type(skillName) == "string" and type(dpsVal) == "number" then
				skillDPS[skillName] = dpsVal
			end
		end
		if next(skillDPS) then
			result.SkillDPS = skillDPS
		end
	end
	return result
end

function commands.get_full_output(params)
	if not build or not build.calcsTab then
		error("No build loaded")
	end
	local output = build.calcsTab.mainOutput
	if not output then
		error("No calculation output available")
	end
	return safeSerialize(output, 0) or {}
end

function commands.get_stat(params)
	if not build or not build.calcsTab then
		error("No build loaded")
	end
	local output = build.calcsTab.mainOutput
	if not output then
		error("No calculation output available")
	end
	
	local key = params.key
	if not key then
		error("Missing 'key' parameter")
	end
	
	local val = output[key]
	if val == nil then
		return { found = false, key = key }
	end
	
	-- For simple values, return directly
	local t = type(val)
	if t == "number" or t == "string" or t == "boolean" then
		return { found = true, key = key, value = val, type = t }
	end
	
	-- For tables, return a preview
	if t == "table" then
		local preview = {}
		local count = 0
		local maxPreview = 10
		for k, v in pairs(val) do
			if type(v) == "number" or type(v) == "string" or type(v) == "boolean" then
				preview[tostring(k)] = v
				count = count + 1
				if count >= maxPreview then
					break
				end
			end
		end
		return { 
			found = true, 
			key = key, 
			type = "table", 
			value = preview,
			table_size = count
		}
	end
	
	-- Other types (function, etc.)
	return { found = true, key = key, type = t, value = tostring(val) }
end

function commands.get_stats_list(params)
	if not build or not build.calcsTab then
		error("No build loaded")
	end
	local output = build.calcsTab.mainOutput
	if not output then
		error("No calculation output available")
	end
	
	local keys = params.keys
	if not keys or type(keys) ~= "table" then
		error("Missing or invalid 'keys' parameter - must be a list of stat keys")
	end
	
	local results = {}
	local notFound = {}
	
	for _, key in ipairs(keys) do
		local val = output[key]
		if val == nil then
			table.insert(notFound, key)
		else
			local t = type(val)
			if t == "number" or t == "string" or t == "boolean" then
				results[key] = { value = val, type = t }
			elseif t == "table" then
				-- For tables, include a preview
				local preview = {}
				local count = 0
				local maxPreview = 5
				for k, v in pairs(val) do
					if type(v) == "number" or type(v) == "string" or type(v) == "boolean" then
						preview[tostring(k)] = v
						count = count + 1
						if count >= maxPreview then
							break
						end
					end
				end
				results[key] = { value = preview, type = "table", table_size = count }
			else
				results[key] = { value = tostring(val), type = t }
			end
		end
	end
	
	return { 
		found = results, 
		not_found = notFound,
		count = #keys,
		found_count = #keys - #notFound
	}
end

-- ============================================================================
-- Modifier tier query commands
-- ============================================================================

function commands.search_modifiers(params)
	if not build or not build.data or not build.data.itemMods then
		error("No build loaded")
	end
	
	local query = (params.query or ""):lower()
	local modType = params.mod_type or "Item" -- "Item", "Flask", "Charm", "Jewel", etc.
	local maxResults = params.max_results or 30
	
	if query == "" then
		error("Missing 'query' parameter")
	end
	
	local modSource = build.data.itemMods[modType]
	if not modSource then
		error("Invalid mod_type: " .. modType)
	end
	
	local groups = {}
	local seenGroups = {}
	local count = 0
	
	for modId, modData in pairs(modSource) do
		-- Check if mod matches query
		local match = false
		if modId:lower():find(query, 1, true) then
			match = true
		elseif modData.affix and modData.affix:lower():find(query, 1, true) then
			match = true
		elseif modData[1] and modData[1]:lower():find(query, 1, true) then
			match = true
		elseif modData.group and modData.group:lower():find(query, 1, true) then
			match = true
		end
		
		if match then
			local group = modData.group or modId
			if not seenGroups[group] then
				seenGroups[group] = true
				
				-- Get tier count for this group
				local tierCount = 0
				for id, data in pairs(modSource) do
					if data.group == group then
						tierCount = tierCount + 1
					end
				end
				
				table.insert(groups, {
					group = group,
					mod_id = modId,
					type = modData.type, -- "Prefix" or "Suffix"
					affix = modData.affix,
					mod_text = modData[1],
					level = modData.level,
					tier_count = tierCount,
					mod_tags = modData.modTags,
				})
				
				count = count + 1
				if count >= maxResults then
					break
				end
			end
		end
	end
	
	-- Sort by level
	table.sort(groups, function(a, b)
		if a.level and b.level then
			return a.level < b.level
		end
		return a.group < b.group
	end)
	
	return { groups = groups, count = count, mod_type = modType }
end

function commands.get_modifier_tiers(params)
	if not build or not build.data or not build.data.itemMods then
		error("No build loaded")
	end
	
	local group = params.group
	local modType = params.mod_type or "Item"
	
	if not group then
		error("Missing 'group' parameter")
	end
	
	local modSource = build.data.itemMods[modType]
	if not modSource then
		error("Invalid mod_type: " .. modType)
	end
	
	local tiers = {}
	
	for modId, modData in pairs(modSource) do
		if modData.group == group then
			-- Extract tier number from modId (e.g., "Strength5" → 5)
			local tierNum = modId:match("%d+$")
			
			table.insert(tiers, {
				mod_id = modId,
				tier = tonumber(tierNum) or 1,
				affix = modData.affix,
				mod_text = modData[1],
				level = modData.level,
				stat_order = modData.statOrder,
				weight_key = modData.weightKey,
				mod_tags = modData.modTags,
			})
		end
	end
	
	-- Sort by tier (ascending)
	table.sort(tiers, function(a, b)
		return a.tier < b.tier
	end)
	
	return { 
		group = group, 
		tiers = tiers, 
		count = #tiers,
		mod_type = modType
	}
end

function commands.get_modifiers_for_item_type(params)
	if not build or not build.data or not build.data.itemMods then
		error("No build loaded")
	end
	
	local itemType = (params.item_type or ""):lower()
	local modType = params.mod_type or "Item"
	local prefixOrSuffix = params.affix_type -- "Prefix", "Suffix", or nil for both
	local maxResults = params.max_results or 50
	
	if itemType == "" then
		error("Missing 'item_type' parameter")
	end
	
	local modSource = build.data.itemMods[modType]
	if not modSource then
		error("Invalid mod_type: " .. modType)
	end
	
	local modifiers = {}
	local seenGroups = {}
	local count = 0
	
	for modId, modData in pairs(modSource) do
		-- Check if this modifier can roll on the item type
		local canRoll = false
		if modData.weightKey and modData.weightVal then
			for i, key in ipairs(modData.weightKey) do
				if key:lower() == itemType or key:lower():find(itemType, 1, true) then
					local weight = modData.weightVal[i]
					if weight and weight > 0 then
						canRoll = true
						break
					end
				end
			end
		end
		
		if canRoll then
			local group = modData.group or modId
			
			-- Filter by prefix/suffix if specified
			if prefixOrSuffix and modData.type ~= prefixOrSuffix then
				canRoll = false
			end
			
			if canRoll and not seenGroups[group] then
				seenGroups[group] = true
				
				-- Count tiers for this group
				local tierCount = 0
				for id, data in pairs(modSource) do
					if data.group == group then
						tierCount = tierCount + 1
					end
				end
				
				table.insert(modifiers, {
					group = group,
					mod_id = modId,
					type = modData.type,
					affix = modData.affix,
					mod_text = modData[1],
					level = modData.level,
					tier_count = tierCount,
					mod_tags = modData.modTags,
				})
				
				count = count + 1
				if count >= maxResults then
					break
				end
			end
		end
	end
	
	-- Sort by level
	table.sort(modifiers, function(a, b)
		if a.level and b.level then
			return a.level < b.level
		end
		return a.group < b.group
	end)
	
	return { 
		modifiers = modifiers, 
		count = count, 
		item_type = itemType,
		mod_type = modType
	}
end

function commands.get_modifier_types(params)
	if not build or not build.data or not build.data.itemMods then
		error("No build loaded")
	end
	
	local types = {}
	for typeName, _ in pairs(build.data.itemMods) do
		table.insert(types, typeName)
	end
	
	-- Sort alphabetically
	table.sort(types)
	
	return { types = types, count = #types }
end

function commands.set_config(params)
	if not build or not build.configTab then
		error("No build loaded")
	end
	local key = params.key
	if not key then
		error("Missing 'key' parameter")
	end
	build.configTab.input[key] = params.value
	build.configTab:BuildModList()
	recalc()
	return { success = true }
end

function commands.set_custom_mods(params)
	if not build then
		error("No build loaded")
	end
	local mods = params.mods
	if not mods then
		error("Missing 'mods' parameter")
	end
	-- Custom mods are typically set on the config tab or through a custom modifier input
	-- Find the custom mods input in the configTab
	if build.configTab and build.configTab.varControls and build.configTab.varControls["customMods"] then
		build.configTab.varControls["customMods"]:SetText(mods)
		build.configTab:BuildModList()
	else
		-- Fallback: set directly in input
		build.configTab.input["customMods"] = mods
		build.configTab:BuildModList()
	end
	recalc()
	return { success = true }
end

function commands.get_builds_path(params)
	return { builds_path = mainObject.main.buildPath }
end

function commands.list_builds(params)
	local subPath = params.sub_path or ""
	local searchPath = mainObject.main.buildPath .. subPath
	local pattern = searchPath .. "*.xml"
	
	local builds = {}
	local folders = {}
	
	-- List XML files (builds)
	local handle = NewFileSearch(pattern, false)
	if handle then
		repeat
			local fileName = handle:GetFileName()
			local modifiedTime = handle:GetFileModifiedTime()
			
			-- Try to extract metadata from the XML file
			local fullPath = searchPath .. fileName
			local file = io.open(fullPath, "r")
			local className, ascendClassName, level, buildName
			
			if file then
				local content = file:read("*a")
				file:close()
				
				-- Extract metadata from XML
				buildName = content:match('<Build [^>]*buildName="([^"]*)"')
				className = content:match('<Player [^>]*className="([^"]*)"')
				ascendClassName = content:match('<Player [^>]*ascendClassName="([^"]*)"')
				level = tonumber(content:match('<Player [^>]*level="(%d+)"')) or 1
			end
			
			table.insert(builds, {
				id = fileName,
				name = buildName or fileName:gsub("%.xml$", ""),
				fileName = fileName,
				fullPath = fullPath,
				level = level or 1,
				className = className,
				ascendClassName = ascendClassName,
				modified = modifiedTime
			})
		until not handle:NextFile()
	end
	
	-- List subdirectories
	local dirHandle = NewFileSearch(searchPath .. "*", true)
	if dirHandle then
		repeat
			local dirName = dirHandle:GetFileName()
			if dirName ~= "." and dirName ~= ".." then
				table.insert(folders, {
					name = dirName,
					fullPath = searchPath .. dirName
				})
			end
		until not dirHandle:NextFile()
	end
	
	return { builds = builds, folders = folders }
end

function commands.load_build_file(params)
	local path = params.path
	if not path then
		error("Missing 'path' parameter")
	end
	
	-- Validate path and get absolute path
	local absPath = validateBuildPath(path, "load")
	
	-- Load the file using absolute path
	local file = io.open(absPath, "r")
	if not file then
		error("File not found: " .. absPath)
	end
	local xmlContent = file:read("*a")
	file:close()
	
	-- Extract name from filename
	local name = absPath:match("([^/\\]+)%.xml$") or absPath
	
	loadBuildFromXML(xmlContent, name)
	return { success = true }
end

function commands.save_build(params)
	if not build then
		error("No build loaded")
	end
	
	if not build.buildFileName then
		error("Build has no file name, use save_build_as instead")
	end
	
	build:SaveDBFile(build.buildFileName)
	return { success = true }
end

function commands.save_build_as(params)
	if not build then
		error("No build loaded")
	end
	
	local name = params.name
	if not name then
		error("Missing 'name' parameter")
	end
	
	local subPath = params.sub_path or ""
	local fileName = name .. ".xml"
	local fullPath = mainObject.main.buildPath .. subPath .. fileName
	
	-- Ensure directory exists
	local dirPath = mainObject.main.buildPath .. subPath
	MakeDir(dirPath)
	
	-- Set the build filename and save
	build.buildFileName = fileName
	build:SaveDBFile(fullPath)
	
	return { success = true, path = fullPath }
end

function commands.delete_build_file(params)
	local path = params.path
	if not path then
		error("Missing 'path' parameter")
	end
	
	-- Validate path and get absolute path
	local absPath = validateBuildPath(path, "delete")
	
	local success = os.remove(absPath)
	if not success then
		error("Failed to delete file: " .. absPath)
	end
	
	return { success = true }
end

function commands.create_folder(params)
	local name = params.name
	if not name then
		error("Missing 'name' parameter")
	end
	
	local subPath = params.sub_path or ""
	local fullPath = mainObject.main.buildPath .. subPath .. name
	
	MakeDir(fullPath)
	return { success = true, path = fullPath }
end

function commands.rename_build_file(params)
	local oldPath = params.old_path
	local newName = params.new_name
	if not oldPath or not newName then
		error("Missing 'old_path' or 'new_name' parameter")
	end
	
	-- Validate old path and get absolute path
	local absOldPath = validateBuildPath(oldPath, "rename")
	
	-- Construct new path (in same directory)
	local dir = absOldPath:match("^(.-)[^/\\]+$") or ""
	local absNewPath = dir .. newName .. ".xml"
	
	-- Validate new path is also within builds directory
	validateBuildPath(absNewPath, "rename target")
	
	local success = os.rename(absOldPath, absNewPath)
	if not success then
		error("Failed to rename file: " .. absOldPath .. " to " .. absNewPath)
	end
	
	return { success = true, new_path = absNewPath }
end

-- ============================================================================
-- Item definition query commands
-- ============================================================================

function commands.search_base_items(params)
	if not build or not build.data then
		error("No build loaded")
	end
	
	local query = (params.query or ""):lower()
	local itemType = params.type -- optional filter by type
	local maxResults = params.max_results or 50
	
	if query == "" and not itemType then
		error("Missing 'query' or 'type' parameter")
	end
	
	local results = {}
	local count = 0
	
	for name, base in pairs(build.data.itemBases) do
		local match = false
		
		-- Check name match
		if query ~= "" then
			if name:lower():find(query, 1, true) then
				match = true
			end
		else
			match = true
		end
		
		-- Check type filter
		if match and itemType then
			local baseType = base.type
			if base.subType then
				baseType = baseType .. ": " .. base.subType
			end
			if baseType:lower() ~= itemType:lower() then
				match = false
			end
		end
		
		if match then
			local result = {
				name = name,
				type = base.type,
				subType = base.subType,
				levelReq = base.req and base.req.level or nil,
				strReq = base.req and base.req.str or nil,
				dexReq = base.req and base.req.dex or nil,
				intReq = base.req and base.req.int or nil,
			}
			
			-- Include implicit mods if any
			if base.implicitModTypes and #base.implicitModTypes > 0 then
				result.implicitCount = #base.implicitModTypes
			end
			
			-- Include weapon data if applicable
			if base.weapon then
				result.weapon = {
					physicalMin = base.weapon.PhysicalMin,
					physicalMax = base.weapon.PhysicalMax,
					attackRate = base.weapon.AttackRate,
					criticalChance = base.weapon.CriticalChance,
					range = base.weapon.Range,
				}
			end
			
			-- Include armour data if applicable
			if base.armour then
				result.armour = base.armour
			end
			
			table.insert(results, result)
			count = count + 1
			if count >= maxResults then
				break
			end
		end
	end
	
	-- Sort results by level requirement, then name
	table.sort(results, function(a, b)
		if a.levelReq and b.levelReq then
			if a.levelReq ~= b.levelReq then
				return a.levelReq < b.levelReq
			end
		elseif a.levelReq then
			return true
		elseif b.levelReq then
			return false
		end
		return a.name < b.name
	end)
	
	return { items = results, count = count }
end

function commands.get_base_item_types(params)
	if not build or not build.data then
		error("No build loaded")
	end
	
	local types = {}
	for _, typeName in ipairs(build.data.itemBaseTypeList) do
		table.insert(types, typeName)
	end
	
	return { types = types, count = #types }
end

function commands.get_base_item_details(params)
	if not build or not build.data then
		error("No build loaded")
	end
	
	local name = params.name
	if not name then
		error("Missing 'name' parameter")
	end
	
	local base = build.data.itemBases[name]
	if not base then
		error("Base item not found: " .. name)
	end
	
	local result = {
		name = name,
		type = base.type,
		subType = base.subType,
		socketLimit = base.socketLimit,
		quality = base.quality,
		tags = base.tags,
		req = base.req,
		implicitModTypes = base.implicitModTypes,
	}
	
	if base.weapon then
		result.weapon = base.weapon
	end
	
	if base.armour then
		result.armour = base.armour
	end
	
	if base.flask then
		result.flask = base.flask
	end
	
	return result
end

function commands.search_unique_items(params)
	if not build or not build.data then
		error("No build loaded")
	end
	
	local query = (params.query or ""):lower()
	local itemType = params.type -- optional filter by type
	local maxResults = params.max_results or 50
	
	if query == "" and not itemType then
		error("Missing 'query' or 'type' parameter")
	end
	
	local results = {}
	local count = 0
	
	for typeName, uniquesList in pairs(build.data.uniques) do
		-- Check type filter
		if itemType and typeName:lower() ~= itemType:lower() then
			goto continue
		end
		
		if type(uniquesList) == "table" then
			for i, uniqueData in ipairs(uniquesList) do
				-- Uniques are stored as strings: first line is name, second line is base
				if type(uniqueData) == "string" then
					local lines = {}
					for line in uniqueData:gmatch("[^\n]+") do
						table.insert(lines, line)
					end
					
					if #lines >= 1 then
						local uniqueName = lines[1]:gsub("^%s*", ""):gsub("%s*$", "")
						local baseName = lines[2] and lines[2]:gsub("^%s*", ""):gsub("%s*$", "") or nil
						
						local match = false
						if query ~= "" then
							if uniqueName:lower():find(query, 1, true) then
								match = true
							elseif baseName and baseName:lower():find(query, 1, true) then
								match = true
							end
						else
							match = true
						end
						
						if match then
							table.insert(results, {
								name = uniqueName,
								baseName = baseName,
								type = typeName,
								index = i,
							})
							count = count + 1
							if count >= maxResults then
								break
							end
						end
					end
				end
			end
		end
		
		::continue::
	end
	
	return { uniques = results, count = count }
end

function commands.get_unique_item_details(params)
	if not build or not build.data then
		error("No build loaded")
	end
	
	local name = params.name
	if not name then
		error("Missing 'name' parameter")
	end
	
	-- Search for the unique across all types
	for typeName, uniquesList in pairs(build.data.uniques) do
		if type(uniquesList) == "table" then
			for i, uniqueData in ipairs(uniquesList) do
				-- Uniques are stored as strings: first line is name
				if type(uniqueData) == "string" then
					local firstLine = uniqueData:match("^([^\n]*)")
					if firstLine then
						local uniqueName = firstLine:gsub("^%s*", ""):gsub("%s*$", "")
						if uniqueName == name then
							-- Found it - parse the full unique definition
							local lines = {}
							for line in uniqueData:gmatch("[^\n]+") do
								local trimmed = (line:gsub("^%s*", ""):gsub("%s*$", ""))
								table.insert(lines, trimmed)
							end
							
							local result = {
								name = lines[1],
								baseName = lines[2],
								type = typeName,
								index = i,
								mods = {},
							}
							
							-- Parse remaining lines as mods (skip variant lines, league lines, etc.)
							for j = 3, #lines do
								local line = lines[j]
								if line ~= "" and not line:match("^Variant:") and not line:match("^League:") then
									table.insert(result.mods, line)
								end
							end
							
							return result
						end
					end
				end
			end
		end
	end
	
	error("Unique item not found: " .. name)
end

function commands.shutdown(params)
	respond({ success = true, message = "Shutting down" })
	os.exit(0)
end

-- ============================================================================
-- Signal ready
-- ============================================================================

ConPrintf("Bridge: Initialization complete, entering command loop")
io.stdout:write(dkjson.encode({ ready = true }) .. "\n")
io.stdout:flush()

-- ============================================================================
-- Main read-eval-respond loop
-- ============================================================================

while true do
	local line = io.stdin:read("*l")
	if not line then
		-- EOF: parent process closed stdin
		ConPrintf("Bridge: stdin closed, exiting")
		break
	end

	-- Skip empty lines
	if line:match("^%s*$") then
		goto continue
	end

	-- Parse the JSON request
	local ok, request = pcall(jsonDecode, line)
	if not ok or type(request) ~= "table" then
		respondError("Invalid JSON: " .. tostring(request))
		goto continue
	end

	local cmd = request.command
	if not cmd then
		respondError("Missing 'command' field")
		goto continue
	end

	local handler = commands[cmd]
	if not handler then
		respondError("Unknown command: " .. tostring(cmd))
		goto continue
	end

	-- Execute the command with error handling
	local execOk, result = pcall(handler, request.params or {})
	if execOk then
		respond(result)
	else
		respondError(tostring(result))
	end

	::continue::
end
