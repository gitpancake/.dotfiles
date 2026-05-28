syntax on
set background=dark

" Gruvbox Material (medium dark)
let g:gruvbox_material_background = 'medium'
let g:gruvbox_material_foreground = 'material'
let g:gruvbox_material_better_performance = 1
silent! colorscheme gruvbox-material

" Fix syntax highlighting loss on scroll in tmux/ghostty
syntax sync minlines=256
set redrawtime=10000
set re=0
autocmd BufEnter,BufWinEnter,WinEnter * syntax sync fromstart

" Truecolor
if has('termguicolors')
  set termguicolors
endif
