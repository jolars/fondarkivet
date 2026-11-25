{ pkgs, ... }:
{
  languages.python = {
    enable = true;
    package = pkgs.python313;
  };
  packages = with pkgs; [ actionlint panache ruff uv ];
  git-hooks.hooks = {
    actionlint.enable = true;
    ruff.enable = true;
    ruff-format.enable = true;
  };
}
