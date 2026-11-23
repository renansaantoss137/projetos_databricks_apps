import os, sys
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')
for img_name in ['logo-dna.png', 'logo_bimbo.png']:
    p = os.path.join('src/app', img_name)
    if os.path.exists(p):
        im = Image.open(p)
        print(f"{img_name}: format={im.format}, size={im.size}, mode={im.mode}")
