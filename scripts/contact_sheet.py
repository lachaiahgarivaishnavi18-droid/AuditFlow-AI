from pathlib import Path
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parents[1]/'output'/'pdf'
pages=sorted(root.glob('final-page-*.png'))
if not pages:raise RuntimeError('Render final PDF pages with pdftoppm first')
width=240;height=360;columns=4
canvas=Image.new('RGB',(columns*width,((len(pages)+columns-1)//columns)*height),'#dbe2e5')
draw=ImageDraw.Draw(canvas)
for i,path in enumerate(pages):
    image=Image.open(path).convert('RGB');image.thumbnail((width-16,height-28))
    x=(i%columns)*width+8;y=(i//columns)*height+20
    canvas.paste(image,(x,y));draw.text((x,y-15),f'Page {i+1}',fill='#253649')
canvas.save(root/'contact-sheet.png')
print(f'{len(pages)} rendered pages; contact sheet saved.')
