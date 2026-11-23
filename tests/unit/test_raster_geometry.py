from PIL import Image, ImageDraw
from pdf2docx_ai.layout.raster_geometry import text_regions


def test_ruled_plan_is_not_replaced_by_ocr_labels():
    image=Image.new('RGB',(600,400),'white');draw=ImageDraw.Draw(image)
    for x in (40,210,380,550):draw.line((x,40,x,350),fill='black',width=4)
    for y in (40,195,350):draw.line((40,y,550,y),fill='black',width=4)
    for x in (80,250,420):
        draw.text((x,90),'A1',fill='black');draw.text((x,240),'B2',fill='black')
    assert text_regions(image)==[]
