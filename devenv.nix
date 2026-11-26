{ lib, pkgs, ... }:
{
  languages.python = {
    enable = true;
    package = pkgs.python313;
  };
  languages.javascript = {
    enable = true;
    package = pkgs.nodejs_24;
  };
  # The npm workerd binary expects a dynamic loader at a conventional Linux path.
  env.MINIFLARE_WORKERD_PATH = lib.mkIf pkgs.stdenv.isLinux (
    toString (
      pkgs.writeShellScript "fondarkivet-workerd" ''
        workerd=$(node -p "require('workerd').default") || exit 1
        exec ${pkgs.stdenv.cc.bintools.dynamicLinker} "$workerd" "$@"
      ''
    )
  );
  packages = with pkgs; [
    actionlint
    panache
    ruff
    uv
  ];
  git-hooks.hooks = {
    actionlint.enable = true;
    ruff.enable = true;
    ruff-format.enable = true;
  };
}
