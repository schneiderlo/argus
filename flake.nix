{
  description = "Development shell for the Argus repository";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python312;
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            bashInteractive
            git
            python
            uv
            nodejs
          ];

          shellHook = ''
            export UV_PYTHON="${python}/bin/python3.12"
            export UV_PYTHON_DOWNLOADS=never

            echo "Argus Nix dev shell"
            echo "python: $(${python}/bin/python3.12 --version 2>&1)"
            echo "uv: $(uv --version 2>&1)"
            echo "node: $(node --version 2>&1)"
            echo "npm: $(npm --version 2>&1)"
            echo
            echo "Repo workflow stays uv-first:"
            echo "  uv sync --group dev"
            echo "  npm --prefix src/argus/render/ui ci"
            echo "  ./scripts/verify.sh"
          '';
        };
      });
}
