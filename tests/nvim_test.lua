-- Drives the Neovim plugin against tests/fake_server.py. Run by test_bridge.py:
--   nvim --headless --clean -l tests/nvim_test.lua <repo> <project> <python> <ihxjava>

local repo, project, python, tool = unpack(arg)
vim.opt.rtp:prepend(repo)
require('ihxjava').setup({ cmd = { python, tool, 'lsp' } })

local function fail(message)
  io.stderr:write(message .. '\n')
  os.exit(1)
end

local function wait_for(what, predicate)
  if not vim.wait(15000, predicate, 50) then
    fail('timed out waiting for ' .. what)
  end
end

local function attached(bufnr)
  local client = vim.lsp.get_clients({ bufnr = bufnr, name = 'intellij' })[1]
  return client ~= nil and client.initialized
end

vim.cmd.edit(project .. '/src/Main.java')
local main = vim.api.nvim_get_current_buf()
wait_for('the client to attach', function() return attached(main) end)
local client = vim.lsp.get_clients({ bufnr = main, name = 'intellij' })[1]
if client.root_dir ~= project then
  fail('root_dir is ' .. tostring(client.root_dir) .. ', expected ' .. project)
end

local params = vim.lsp.util.make_position_params(0, client.offset_encoding)
local response = client:request_sync('textDocument/definition', params, 10000, main)
if not response or response.err then
  fail('definition failed: ' .. vim.inspect(response))
end
local location = response.result[1]
if not vim.uri_to_fname(location.uri):match('/ihxjava/decompiled/%x+/Foo_Inner%.java$') then
  fail('unexpected location ' .. location.uri)
end

vim.lsp.util.show_document(location, client.offset_encoding, { focus = true })
local decompiled = vim.api.nvim_get_current_buf()
wait_for('the decompiled class to attach', function() return attached(decompiled) end)
if #vim.lsp.get_clients({ name = 'intellij' }) ~= 1 then
  fail('opening the decompiled class started a second server')
end
if not vim.bo[decompiled].readonly then
  fail('the decompiled class is writable')
end

local opened = client:request_sync('test/opened', {}, 10000, main).result
if not vim.list_contains(opened, 'jar:file:///libs/acme-1.0.jar!/com/acme/Foo$Inner.class') then
  fail('the server saw these documents open: ' .. vim.inspect(opened))
end

client:stop()
wait_for('the client to stop', function() return client:is_stopped() end)
os.exit(0)
