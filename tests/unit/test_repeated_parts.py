from pdf2docx_ai.document.models import BBox, Document, Page, Region
from pdf2docx_ai.pipeline import _mark_repeated_parts


def test_repeated_edge_text_is_independent_of_pdf_block_grouping():
    def r(page,text,x,y,width=180):
        return Region(page_number=page,text=text,bbox=BBox(x0=x,y0=y,x1=x+width,y1=y+10))
    pages=[]
    for number in (1,2):
        edge=([r(1,'LABORATORY',50,20),r(1,'REPORT EX-1',320,20)] if number==1
              else [r(2,'LABORATORY\tREPORT EX-2',50,20,450)])
        foot=([r(1,'Demonstration corpus',50,760),r(1,'Page 1',320,760)] if number==1
              else [r(2,'Demonstration corpus\tPage 2',50,760,450)])
        pages.append(Page(number=number,width=600,height=800,classification='native',
            cropbox=BBox(x0=0,y0=0,x1=600,y1=800),regions=edge+[r(number,'Body '+str(number),50,150)]+foot))
    doc=Document(source_path='fictitious.pdf',source_sha256='0'*64,pages=pages)
    _mark_repeated_parts(doc)
    assert sum(r.kind=='header' for p in doc.pages for r in p.regions)==3
    assert sum(r.kind=='footer' for p in doc.pages for r in p.regions)==3
    assert all(r.kind=='text' for p in doc.pages for r in p.regions if r.text.startswith('Body'))
