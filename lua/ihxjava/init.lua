-- Neovim (0.11+) setup for `ihxjava lsp`, JetBrains' IntelliJ language server for Java and Kotlin.
--
--   require('ihxjava').setup()
--   require('ihxjava').setup({ init_options = { buildTool = 'gradle' } })
--
-- Any field accepted by `vim.lsp.config()` can be passed and overrides the default.

local M = {}

local function decompiled_dir()
  local base = os.getenv('XDG_CACHE_HOME')
  if base == nil or base:sub(1, 1) ~= '/' then
    base = vim.fn.expand('~/.cache')
  end
  return vim.fs.normalize(base .. '/ihxjava/decompiled')
end

--- The top of the project, not the nearest module: IntelliJ imports the whole build.
local function project_root(bufnr)
  return vim.fs.root(bufnr, { 'settings.gradle', 'settings.gradle.kts', 'MODULE.bazel', 'WORKSPACE' })
    or vim.fs.root(bufnr, '.git')
    or vim.fs.root(bufnr, { 'pom.xml', 'build.gradle', 'build.gradle.kts' })
end

function M.setup(config)
  if vim.fn.has('nvim-0.11') == 0 then
    vim.notify('ihxjava needs Neovim 0.11 or later', vim.log.levels.ERROR)
    return
  end
  local decompiled = decompiled_dir()

  vim.lsp.config('intellij', vim.tbl_deep_extend('force', {
    cmd = { 'ihxjava', 'lsp' },
    filetypes = { 'java', 'kotlin' },
    root_dir = function(bufnr, on_dir)
      local name = vim.fs.normalize(vim.api.nvim_buf_get_name(bufnr))
      if vim.startswith(name, decompiled .. '/') then
        -- A decompiled library class belongs to the server that produced it.
        local client = vim.lsp.get_clients({ name = 'intellij' })[1]
        if client then
          on_dir(client.root_dir)
        end
        return
      end
      local root = project_root(bufnr)
      if root then
        on_dir(root)
      end
    end,
    init_options = {},
  }, config or {}))
  vim.lsp.enable('intellij')
end

return M
