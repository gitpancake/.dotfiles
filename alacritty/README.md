# Alacritty

Config + Gruvbox Material themes from [alacritty/alacritty-theme](https://github.com/alacritty/alacritty-theme).

## Files
- `alacritty.toml` — main config (imports medium-dark theme by default)
- `themes/gruvbox_material_medium_dark.toml`
- `themes/gruvbox_material_medium_light.toml`
- `themes/gruvbox_material_hard_dark.toml`

## Install
`install-mac.sh` symlinks:
- `alacritty.toml` → `~/.config/alacritty/alacritty.toml`
- `themes/` → `~/.config/alacritty/themes`

## Switch theme
Edit `import` in `alacritty.toml`. Alacritty hot-reloads on save (`live_config_reload = true`).
