"""Generate complex, fictitious reference DOCX/PDF pairs for layout regression.

All text is original synthetic content. Native sections, columns, tabs, actual
data tables and independent images are used; never layout tables or text boxes.
Generated source references are distinct from converter output. No downloads.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from docx import Document
from docx.enum.section import WD_SECTION_START, WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from PIL import Image, ImageDraw
try:
    import pymupdf
except ImportError:
    pymupdf=None

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT=ROOT/"tests/fixtures/complex/generated"
ASSETS=ROOT/"tests/fixtures/complex/assets"
INK="183B50"
MUTED="426176"
BLUE="246580"


def xml(tag,attrs=None,text=None):
    element=OxmlElement(tag)
    for key,value in (attrs or {}).items(): element.set(qn(key),str(value))
    if text is not None: element.text=text
    return element


def field(paragraph,instruction):
    item=xml("w:fldSimple",{"w:instr":instruction})
    item.append(xml("w:r"));paragraph._p.append(item)


def section_setup(section,landscape=False,margin=51):
    section.page_width=Pt(842 if landscape else 595)
    section.page_height=Pt(595 if landscape else 842)
    section.orientation=WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    section.left_margin=Pt(margin);section.right_margin=Pt(margin)
    section.top_margin=Pt(54);section.bottom_margin=Pt(48)
    section.header_distance=Pt(23);section.footer_distance=Pt(22)


def columns(section,widths=None,count=2,gap=23):
    existing=section._sectPr.find(qn("w:cols"))
    if existing is not None: section._sectPr.remove(existing)
    cols=xml("w:cols",{"w:num":len(widths) if widths else count,"w:space":round(gap*20),"w:equalWidth":0 if widths else 1})
    if widths:
        for i,width in enumerate(widths): cols.append(xml("w:col",{"w:w":round(width*20),"w:space":round(gap*20) if i<len(widths)-1 else 0}))
    section._sectPr.append(cols)


def base(title,code,font="Arial",size=10.5):
    doc=Document();section_setup(doc.sections[0])
    doc.core_properties.title=title;doc.core_properties.author="PDF2DOCX AI synthetic corpus"
    doc.core_properties.subject="Reference document with wholly fictitious content"
    normal=doc.styles["Normal"];normal.font.name=font;normal.font.size=Pt(size)
    normal.paragraph_format.line_spacing=Pt(size*1.24)
    normal.paragraph_format.space_after=Pt(5)
    normal.paragraph_format.widow_control=True
    for name,fontsize in (("Title",25),("Heading 1",14),("Heading 2",11.5)):
        style=doc.styles[name];style.font.name=font;style.font.size=Pt(fontsize);style.font.color.rgb=RGBColor.from_string(INK)
        style.paragraph_format.space_before=Pt(13 if name!="Title" else 0)
        style.paragraph_format.space_after=Pt(6)
        style.paragraph_format.keep_with_next=True
    doc.styles["Title"].font.bold=True
    header=doc.sections[0].header.paragraphs[0]
    header.paragraph_format.space_after=Pt(0)
    header.paragraph_format.tab_stops.add_tab_stop(Pt(493),WD_TAB_ALIGNMENT.RIGHT)
    run=header.add_run("LABORATORIO ESEMPIO\t"+code);run.font.name=font;run.font.size=Pt(8);run.font.color.rgb=RGBColor.from_string(MUTED)
    footer=doc.sections[0].footer.paragraphs[0]
    footer.paragraph_format.space_after=Pt(0)
    footer.paragraph_format.tab_stops.add_tab_stop(Pt(493),WD_TAB_ALIGNMENT.RIGHT)
    run=footer.add_run("Dati interamente fittizi • Corpus di regressione\tPagina ");run.font.size=Pt(8);run.font.color.rgb=RGBColor.from_string(MUTED)
    field(footer,"PAGE")
    return doc


def para(doc,text,style=None,before=0,after=5,size=None,font=None,bold=False,color=None,indent=0,align=None):
    p=doc.add_paragraph(style=style)
    p.paragraph_format.space_before=Pt(before);p.paragraph_format.space_after=Pt(after)
    p.paragraph_format.left_indent=Pt(indent)
    if align is not None: p.alignment=align
    run=p.add_run(text);run.bold=bold
    if size: run.font.size=Pt(size)
    if font: run.font.name=font
    if color: run.font.color.rgb=RGBColor.from_string(color)
    return p


def h(doc,text,level=1): return para(doc,text,f"Heading {level}")


def bullet(doc,text,level=0):
    p=para(doc,"• "+text,after=3,indent=11+level*12)
    p.paragraph_format.first_line_indent=Pt(-10)
    return p


def dated(doc,date,title,details=None):
    p=doc.add_paragraph();p.paragraph_format.space_before=Pt(7);p.paragraph_format.space_after=Pt(3)
    p.paragraph_format.left_indent=Pt(112);p.paragraph_format.first_line_indent=Pt(-112)
    p.paragraph_format.tab_stops.add_tab_stop(Pt(112))
    run=p.add_run(date+"\t");run.font.size=Pt(9);run.font.color.rgb=RGBColor.from_string(MUTED)
    p.add_run(title).bold=True
    p.paragraph_format.keep_with_next=True
    if details: para(doc,details,indent=112,after=5)
    return p


def table(doc,headers,rows,widths,merges=()):
    t=doc.add_table(rows=1,cols=len(headers));t.autofit=False;t.alignment=WD_TABLE_ALIGNMENT.LEFT
    t.style="Table Grid"
    for c,w in zip(t.columns,widths): c.width=Pt(w)
    for i,text in enumerate(headers): t.cell(0,i).text=text
    t.rows[0]._tr.get_or_add_trPr().append(xml("w:tblHeader"))
    for values in rows:
        cells=t.add_row().cells
        for i,text in enumerate(values): cells[i].text=str(text)
    for ri,row in enumerate(t.rows):
        row._tr.get_or_add_trPr().append(xml("w:cantSplit"))
        for ci,cell in enumerate(row.cells):
            cell.width=Pt(widths[ci]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            props=cell._tc.get_or_add_tcPr()
            mar=xml("w:tcMar")
            for side in ("top","bottom","left","right"): mar.append(xml("w:"+side,{"w:w":70,"w:type":"dxa"}))
            props.append(mar)
            for p in cell.paragraphs:
                p.paragraph_format.space_after=Pt(1);p.paragraph_format.space_before=Pt(1)
                p.paragraph_format.line_spacing=Pt(12)
                for r in p.runs: r.font.size=Pt(9);r.bold=ri==0
            if ri==0: props.append(xml("w:shd",{"w:fill":"EAF0F4"}))
    for a,b,c,d in merges: t.cell(a,b).merge(t.cell(c,d))
    doc.add_paragraph().paragraph_format.space_after=Pt(0)
    return t


def anchor(picture,x,y,wrap="square",behind=False):
    inline=picture._inline
    a=xml("wp:anchor")
    for key,value in dict(distT=0,distB=0,distL=114300,distR=114300,simplePos=0,relativeHeight=1,behindDoc=int(behind),locked=0,layoutInCell=1,allowOverlap=1).items(): a.set(key,str(value))
    pos=xml("wp:simplePos");pos.set("x","0");pos.set("y","0");a.append(pos)
    for tag,offset in (("H",x),("V",y)):
        node=xml("wp:position"+tag);node.set("relativeFrom","page")
        node.append(xml("wp:posOffset",text=str(round(offset*12700))));a.append(node)
    for child in list(inline):
        if child.tag in (qn("wp:extent"),qn("wp:effectExtent")):a.append(child)
    wrapping=xml("wp:wrapSquare" if wrap=="square" else "wp:wrapNone")
    if wrap=="square":wrapping.set("wrapText","bothSides")
    a.append(wrapping)
    for child in list(inline):a.append(child)
    inline.getparent().replace(inline,a)


def float_image(doc,path,x,y,width,height,wrap="square"):
    p=doc.add_paragraph();p.paragraph_format.space_after=Pt(0);p.paragraph_format.line_spacing=Pt(1)
    picture=p.add_run().add_picture(str(path),width=Pt(width),height=Pt(height))
    anchor(picture,x,y,wrap)
    return p


def rule(doc,text):
    p=para(doc,text,bold=True,color=BLUE,before=9,after=8)
    border=xml("w:pBdr");border.append(xml("w:bottom",{"w:val":"single","w:sz":8,"w:color":"246580","w:space":5}))
    p._p.get_or_add_pPr().append(border)
    return p


def assets():
    ASSETS.mkdir(parents=True,exist_ok=True)
    # Code-native original charts and logo; no photos or data from third parties.
    logo=Image.new("RGB",(420,100),"white");draw=ImageDraw.Draw(logo)
    draw.rounded_rectangle((5,5,90,90),18,fill="#246580");draw.polygon([(23,65),(48,20),(75,65)],fill="white")
    draw.text((110,34),"AURORA / LAB",fill="#183B50",font_size=30)
    logo.save(ASSETS/"aurora-logo.png")
    chart=Image.new("RGB",(900,550),"white");draw=ImageDraw.Draw(chart)
    for y in range(80,450,70):draw.line((75,y,840,y),fill="#d9e2e8",width=2)
    vals=[(75,380),(210,330),(340,350),(475,240),(610,210),(745,125),(840,90)]
    draw.line(vals,fill="#246580",width=9)
    for x,y in vals:draw.ellipse((x-8,y-8,x+8,y+8),fill="#d58d48")
    draw.line((75,55,75,455),fill="#183B50",width=3);draw.line((75,455,845,455),fill="#183B50",width=3)
    draw.text((80,485),"Q1     Q2     Q3     Q4     Q5     Q6",fill="#426176",font_size=30)
    chart.save(ASSETS/"trend-chart.png")
    plan=Image.new("RGB",(800,530),"#f8fafb");draw=ImageDraw.Draw(plan)
    draw.rectangle((70,55,730,465),outline="#183B50",width=10)
    for x in (290,510):draw.line((x,55,x,465),fill="#246580",width=8)
    draw.line((70,260,730,260),fill="#246580",width=8)
    for x,y,label in ((120,110,"A1"),(340,110,"A2"),(560,110,"A3"),(120,320,"B1"),(340,320,"B2"),(560,320,"B3")):draw.text((x,y),label,fill="#183B50",font_size=48)
    plan.save(ASSETS/"site-plan.png")
    portrait=ASSETS/"fictional-cv-portrait.png"
    if not portrait.exists():
        # An explicitly illustrated fictional portrait is a deterministic fallback.
        im=Image.new("RGB",(400,500),"#dce5ea");draw=ImageDraw.Draw(im)
        draw.ellipse((82,42,318,280),fill="#483b34");draw.rounded_rectangle((115,90,285,325),80,fill="#d6a789")
        draw.polygon([(45,500),(75,360),(155,310),(245,310),(325,360),(365,500)],fill="#29485e")
        draw.polygon([(155,310),(200,395),(245,310)],fill="white")
        draw.ellipse((148,175,157,184),fill="#282828");draw.ellipse((242,175,251,184),fill="#282828")
        draw.arc((168,215,234,250),0,180,fill="#7b473d",width=4);im.save(portrait)
    return portrait


def cv(portrait):
    doc=base("Curriculum europeo di Elena Esempio","CV-EX-001",size=10.2)
    float_image(doc,portrait,439,63,100,125)
    p=para(doc,"ELENA ESEMPIO","Title",after=5);p.paragraph_format.right_indent=Pt(115)
    para(doc,"Project manager per servizi digitali pubblici",bold=True,color=BLUE,size=12,after=9)
    for text in ("⌂ Valleverde, Italia · dati anagrafici fittizi","@ elena.esempio@example.invalid","Tel. +39 000 000 0000 · Profilo CV-EX-001"):
        para(doc,text,size=9.5,after=3)
    para(doc,"CURRICULUM DI PROVA · persona e incarichi completamente inventati",size=8,color=MUTED,after=14)
    rule(doc,"PROFILO PROFESSIONALE")
    para(doc,"Coordino progetti di trasformazione digitale dalla raccolta dei requisiti alla verifica del servizio. Ho esperienza nella gestione di gruppi multidisciplinari, nell'analisi dei processi e nella definizione di indicatori misurabili. Lavoro con amministrazioni e fornitori mantenendo tracciabilità delle decisioni, accessibilità dei contenuti e controllo delle scadenze.")
    rule(doc,"ESPERIENZA PROFESSIONALE")
    dated(doc,"2022 - oggi","Responsabile di progetto","Laboratorio Aurora Esempio · Valleverde, Italia")
    for text in ("Coordinamento di un programma dimostrativo di sportelli digitali per sei sedi territoriali.","Pianificazione delle attività di dodici professionisti e revisione mensile dei rischi.","Introduzione di un catalogo di requisiti con versionamento e criteri di accettazione."):
        p=bullet(doc,text);p.paragraph_format.left_indent=Pt(123)
    dated(doc,"2018 - 2022","Analista di processi e servizi","Consorzio Dimostrativo Esempio · Borgonuovo, Italia")
    for text in ("Mappatura dei flussi documentali e delle responsabilità tra uffici.","Preparazione di capitolati, scenari di test e materiali di formazione.","Verifica dei risultati con utenti pilota e registrazione delle anomalie rilevate."):
        p=bullet(doc,text);p.paragraph_format.left_indent=Pt(123)
    rule(doc,"ISTRUZIONE E FORMAZIONE")
    dated(doc,"2016 - 2018","Laurea magistrale in gestione dell'innovazione","Università Dimostrativa di Valleverde · Voto e corso fittizi")
    dated(doc,"2013 - 2016","Laurea in economia e organizzazione","Istituto Universitario Esempio · Percorso sintetico di regressione")
    doc.add_page_break()
    h(doc,"Competenze e progetti",1)
    para(doc,"Le competenze riportate hanno funzione esclusivamente dimostrativa. La distribuzione tra righe, date, tabulazioni e sezioni costituisce parte del test di ricostruzione.",size=9.5)
    rule(doc,"COMPETENZE LINGUISTICHE")
    table(doc,["Lingua","Comprensione","Interazione","Scrittura"],[["Italiano","Madrelingua","Madrelingua","Madrelingua"],["Inglese","C1","B2","C1"],["Francese","B1","B1","B1"]],[115,126,126,126])
    rule(doc,"COMPETENZE DIGITALI E ORGANIZZATIVE")
    for title,text in (("Gestione di progetto","Pianificazione per milestone, gestione del budget, analisi dei rischi e rendicontazione periodica."),("Analisi e qualità","Modellazione dei processi, definizione di indicatori, test di accettazione e revisione dei documenti."),("Collaborazione","Facilitazione di workshop, scrittura tecnica, coordinamento di fornitori e gestione delle dipendenze.")):
        dated(doc,title,"",text)
    rule(doc,"PROGETTI SELEZIONATI")
    dated(doc,"2024 - 2025","Sportello Unico Esempio","Portale dimostrativo per pratiche amministrative con catalogo dei procedimenti e monitoraggio delle richieste.")
    dated(doc,"2021 - 2022","Archivio Aperto Dimostrativo","Revisione dei metadati di un archivio documentale e definizione di controlli ripetibili sulla qualità dei contenuti.")
    rule(doc,"CERTIFICAZIONI E ATTIVITÀ")
    bullet(doc,"Percorso fittizio di formazione in accessibilità digitale, edizione 2025.")
    bullet(doc,"Seminario dimostrativo su interoperabilità, protezione dei dati e progettazione dei servizi.")
    para(doc,"Autorizzazione: tutti i dati e la fotografia di questo curriculum sono sintetici. Nessuna informazione identifica una persona reale.",size=8.5,before=12,color=MUTED)
    return doc


REPORT_PARAS=[
    "Il progetto prende in esame un insieme dimostrativo di servizi territoriali. L'analisi è costruita con dati fittizi e serve a verificare la continuità della lettura quando il documento presenta più blocchi, font e vincoli di impaginazione. Ogni risultato deve essere interpretato nel contesto delle ipotesi dichiarate e delle limitazioni del campione.",
    "La raccolta è stata organizzata in cicli di osservazione, revisione e verifica. I gruppi hanno registrato le attività mediante un repertorio condiviso, distinguendo le richieste iniziali dalle modifiche approvate. La procedura consente di ricostruire le decisioni e riduce le ambiguità nelle fasi di consegna.",
    "Per confrontare le alternative è stato definito un quadro di indicatori indipendenti. Tempo, costo, qualità documentale e accessibilità vengono misurati separatamente, evitando che un valore medio favorevole nasconda casi critici. Le soglie sono obiettivi del progetto e non proprietà garantite del processo.",
    "La revisione ha evidenziato l'importanza delle relazioni tra elementi adiacenti. Una didascalia deve restare associata alla figura, una riga di intestazione deve ripetersi nelle tabelle lunghe e un titolo non deve essere isolato dal paragrafo successivo. Queste condizioni sono verificabili anche dopo la conversione.",
]


def research(_):
    doc=base("Quaderno di ricerca territoriale","RIC-2026-014",font="Times New Roman",size=10.5)
    para(doc,"Quaderno di ricerca territoriale","Title")
    para(doc,"Confronto di metodi per l'osservazione dei servizi",size=13,bold=True)
    para(doc,"Gruppo Ricerca Esempio · Edizione sperimentale · Novembre 2026",size=9,color=MUTED)
    para(doc,"Abstract",bold=True)
    para(doc,REPORT_PARAS[0])
    s=doc.add_section(WD_SECTION_START.CONTINUOUS);columns(s,count=2,gap=24)
    for i,title in enumerate(("1 Introduzione","2 Disegno della ricerca","3 Indicatori e osservazioni","4 Discussione dei risultati")):
        h(doc,title,2)
        for k in range(2):para(doc,REPORT_PARAS[(i+k)%len(REPORT_PARAS)])
    doc.add_page_break()
    for i,title in enumerate(("5 Confronto dei casi","6 Limiti del campione","7 Risultati operativi","8 Conclusioni")):
        h(doc,title,2)
        para(doc,REPORT_PARAS[(i+1)%4]);para(doc,REPORT_PARAS[(i+2)%4])
    return doc


def administration(_):
    doc=base("Relazione di istruttoria amministrativa","AMM-2026-008")
    doc.add_picture(str(ASSETS/"aurora-logo.png"),width=Pt(168))
    doc.paragraphs[-1].paragraph_format.line_spacing=1.0
    para(doc,"Comune dimostrativo di Valleverde","Title")
    p=para(doc,"Protocollo EX-248/2026\tValleverde, 16 novembre 2026",size=9.5)
    p.paragraph_format.tab_stops.add_tab_stop(Pt(493),WD_TAB_ALIGNMENT.RIGHT)
    para(doc,"Oggetto: verifica del progetto di servizio territoriale",bold=True,before=15)
    para(doc,"Alla Commissione tecnica di prova\nArea servizi e innovazione\nSede dimostrativa",indent=285,before=8,after=15)
    for i,title in enumerate(("Premessa","Documentazione esaminata","Verifica dei requisiti")):
        h(doc,title,2);para(doc,REPORT_PARAS[i]);para(doc,REPORT_PARAS[(i+1)%4])
    doc.add_page_break();h(doc,"Esito della verifica",1)
    table(doc,["Requisito","Evidenza","Esito"],[["Accessibilità","Verbale dimostrativo EX-12","Conforme"],["Continuità del servizio","Prova su ambiente sintetico","Da integrare"],["Tracciabilità","Registro delle decisioni EX-17","Conforme"],["Formazione","Piano operativo e calendario","Conforme"]],[130,280,83])
    for i,title in enumerate(("Prescrizioni operative","Responsabilità e scadenze","Conclusione")):
        h(doc,title,2);para(doc,REPORT_PARAS[(i+2)%4])
    para(doc,"Il responsabile del procedimento\nDott.ssa Persona Fittizia",indent=280,before=20)
    return doc


def invoice(_):
    doc=base("Prospetto economico e fattura dimostrativa","FAT-EX-027",size=10)
    para(doc,"Fattura dimostrativa","Title")
    para(doc,"Aurora Servizi Esempio S.r.l. · Partita IVA fittizia IT00000000000",bold=True)
    para(doc,"Via del Documento 12, 00000 Valleverde · amministrazione@example.invalid",size=9)
    p=para(doc,"Numero EX-027/2026\tData 16/11/2026",before=10);p.paragraph_format.tab_stops.add_tab_stop(Pt(493),WD_TAB_ALIGNMENT.RIGHT)
    para(doc,"Destinatario: Ente Dimostrativo Progetti · Codice cliente EX-018",before=7,after=10)
    rows=[];group_rows=[]
    for i in range(1,31):
        if i in (1,11,21):
            group_rows.append(len(rows)+1)
            rows.append([f"FASE {chr(65+(i-1)//10)}  Servizi di analisi e consegna", "", "", "", ""])
        rows.append([f"S{i:02d}",f"Servizio dimostrativo fase {i}: verifica e documentazione",str(i%4+1),f"{45+i:,.2f}",f"{(i%4+1)*(45+i):,.2f}"])
    items=table(doc,["Codice","Descrizione","Q.tà","Prezzo EUR","Importo EUR"],rows,[48,255,36,75,79],merges=[(r,0,r,4) for r in group_rows])
    for i,r in enumerate(group_rows):
        items.cell(r,0).text=f"FASE {chr(65+i)}  Servizi di analisi e consegna"
        items.cell(r,0)._tc.get_or_add_tcPr().append(xml("w:shd",{"w:fill":"F2F5F7"}))
    para(doc,"Riepilogo economico",bold=True,before=10)
    t=table(doc,["Voce","Importo EUR"],[["Imponibile dimostrativo","4.380,00"],["IVA dimostrativa 22%","963,60"],["Totale documento","5.343,60"]],[380,113])
    for cell in t.rows[-1].cells:
        for p in cell.paragraphs:
            for r in p.runs:r.bold=True
    para(doc,"Condizioni: documento privo di valore fiscale. Importi e soggetti sono inventati; il prospetto verifica la continuità di una tabella autentica su più pagine.",size=8.5,before=8)
    return doc


def inspection(_):
    doc=base("Verbale di sopralluogo tecnico","ISP-EX-011",size=10.5)
    para(doc,"Verbale di sopralluogo tecnico","Title")
    para(doc,"Sede dimostrativa Valleverde · Area B · 16 novembre 2026",size=9,color=MUTED)
    h(doc,"1 Stato dei locali",2)
    float_image(doc,ASSETS/"site-plan.png",345,151,195,129)
    for text in REPORT_PARAS[:3]:para(doc,text)
    para(doc,"Figura 1 · Pianta sintetica della sede dimostrativa",size=8.5,color=MUTED,align=WD_ALIGN_PARAGRAPH.RIGHT)
    h(doc,"2 Osservazioni",2)
    for i in range(4):bullet(doc,f"Area {chr(65+i)}: verifica delle dotazioni, dei percorsi e della disponibilità della documentazione tecnica.")
    doc.add_page_break();h(doc,"3 Misure e azioni correttive",1)
    table(doc,["Area","Rilievo sintetico","Azione","Scadenza"],[["A1","Segnaletica da completare","Aggiornare repertorio","30/11/2026"],["A2","Dotazioni verificate","Nessun intervento","-"],["B1","Registro non aggiornato","Integrare cronologia","15/12/2026"],["B3","Percorso da verificare","Prova con utenti fittizi","20/12/2026"]],[45,198,160,90])
    for i in range(3):h(doc,f"3.{i+1} Prescrizione operativa",2);para(doc,REPORT_PARAS[i])
    return doc


def mixed_orientation(_):
    doc=base("Piano operativo e allegati","PIA-EX-006")
    para(doc,"Piano operativo e allegati","Title")
    for i,title in enumerate(("Contesto e obiettivi","Organizzazione","Calendario delle verifiche")):
        h(doc,title,2);para(doc,REPORT_PARAS[i]);para(doc,REPORT_PARAS[(i+1)%4])
    s=doc.add_section(WD_SECTION_START.NEW_PAGE);section_setup(s,landscape=True)
    h(doc,"Allegato A  Matrice delle responsabilità",1)
    table(doc,["Attività"]+[f"Fase {i}" for i in range(1,9)],[[f"Azione {i}: verifica dimostrativa"]+["R" if (i+j)%3==0 else "C" if (i+j)%3==1 else "I" for j in range(8)] for i in range(1,12)],[220]+[65]*8)
    para(doc,"Legenda: R responsabile, C consultato, I informato. Tutte le attribuzioni sono fittizie.",size=9)
    s=doc.add_section(WD_SECTION_START.NEW_PAGE);section_setup(s)
    h(doc,"Allegato B  Criteri di accettazione",1)
    for i in range(4):h(doc,f"B.{i+1} Controllo di qualità",2);para(doc,REPORT_PARAS[i])
    return doc


def typography(_):
    doc=base("Manuale di scrittura tecnica","TIP-EX-004",font="Arial")
    para(doc,"Manuale di scrittura tecnica","Title")
    for font,title in (("Arial","Testo informativo"),("Times New Roman","Citazione e commento"),("Courier New","Codice e valori numerici")):
        h(doc,title,2)
        para(doc,REPORT_PARAS[0] if font!="Courier New" else "record_id = EX_004\nversione = 2026.11\nimporto = 12345.67\nstato = verificato",font=font,size=10 if font=="Courier New" else 11.5)
    p=doc.add_paragraph();p.add_run("Caratteri in grassetto ").bold=True;p.add_run("e corsivo ").italic=True
    r=p.add_run("con colore originale");r.font.color.rgb=RGBColor.from_string("784C6C")
    para(doc,"Numeri e simboli: 12,50 EUR; 08/11/2026; 25%; à è ì ò ù; x² + y² = z².",before=10)
    doc.add_page_break();h(doc,"Variazioni di gerarchia e rientro",1)
    for i in range(4):
        p=para(doc,REPORT_PARAS[i],font="Times New Roman",size=11,indent=i*14)
        p.paragraph_format.first_line_indent=Pt(14 if i%2==0 else -10)
        p.paragraph_format.line_spacing=Pt(15+i)
    h(doc,"Note di applicazione",2);para(doc,REPORT_PARAS[3],font="Arial",size=10.5)
    return doc


def statement(_):
    doc=base("Rendiconto di progetto","REN-HO-002",font="Times New Roman",size=10.5)
    para(doc,"Rendiconto di progetto","Title")
    para(doc,"Periodo di riferimento gennaio ottobre 2026",size=12,bold=True)
    for label,value in (("Ente beneficiario","Fondazione Dimostrativa Esempio"),("Progetto","Ponte Aperto EX-092"),("Responsabile","Persona Fittizia")):
        p=para(doc,label+"\t"+value);p.paragraph_format.tab_stops.add_tab_stop(Pt(150))
    h(doc,"1 Quadro di sintesi",2);para(doc,REPORT_PARAS[2])
    table(doc,["Voce","Preventivo","Impegnato","Pagato","Scostamento"],[[label,*values] for label,values in [("Personale",("42.000,00","38.000,00","34.500,00","4.000,00")),("Servizi",("18.000,00","16.800,00","15.000,00","1.200,00")),("Dotazioni",("9.500,00","9.100,00","8.800,00","400,00")),("Spese generali",("4.500,00","4.000,00","3.500,00","500,00"))]],[150,86,86,86,85])
    h(doc,"2 Commento agli scostamenti",2);para(doc,REPORT_PARAS[1]);para(doc,REPORT_PARAS[3])
    doc.add_page_break();h(doc,"3 Dettaglio delle operazioni",1)
    for i in range(1,11):
        p=para(doc,f"{i:02d}/10/2026\tMandato EX-{300+i}\t{180+i*37:,.2f} EUR",after=5)
        p.paragraph_format.tab_stops.add_tab_stop(Pt(115));p.paragraph_format.tab_stops.add_tab_stop(Pt(493),WD_TAB_ALIGNMENT.RIGHT)
    h(doc,"4 Dichiarazione finale",2);para(doc,REPORT_PARAS[0]);para(doc,"Documento di prova senza valore contabile. Tutte le operazioni, le date e gli importi sono sintetici.",size=9,color=MUTED)
    return doc


def newsletter(_):
    doc=base("Notiziario dei servizi di quartiere","NOT-HO-003",font="Arial",size=10)
    para(doc,"Notiziario dei servizi di quartiere","Title")
    para(doc,"Edizione dimostrativa  Novembre 2026",size=10,color=MUTED,after=12)
    s=doc.add_section(WD_SECTION_START.CONTINUOUS);columns(s,widths=[170,300],gap=23)
    h(doc,"In breve",2)
    for i in range(3):h(doc,f"Avviso {i+1}",2);para(doc,REPORT_PARAS[i][:175]+".",size=9)
    doc.add_paragraph().add_run().add_break(WD_BREAK.COLUMN)
    h(doc,"Un percorso condiviso",1);para(doc,REPORT_PARAS[0]);para(doc,REPORT_PARAS[1])
    doc.add_picture(str(ASSETS/"trend-chart.png"),width=Pt(285))
    doc.paragraphs[-1].paragraph_format.line_spacing=1.0
    para(doc,"Figura 2  Andamento di un indicatore dimostrativo",size=8,color=MUTED)
    para(doc,REPORT_PARAS[2])
    s=doc.add_section(WD_SECTION_START.NEW_PAGE);columns(s,widths=[210,260],gap=23)
    for i in range(4):h(doc,f"Proposta {i+1}",2);para(doc,REPORT_PARAS[i])
    return doc


def procurement(_):
    doc=base("Scheda di valutazione tecnica","VAL-HO-005",font="Arial",size=10.5)
    para(doc,"Scheda di valutazione tecnica","Title")
    for label,value in (("Procedura","EX-2026-105"),("Oggetto","Servizi documentali dimostrativi"),("Commissione","Gruppo Tecnico Esempio")):
        p=para(doc,label+"\t"+value,after=7);p.paragraph_format.tab_stops.add_tab_stop(Pt(130))
    rule(doc,"CRITERI E PUNTEGGI")
    scores=table(doc,["Criterio","Max","Offerta A","Offerta B","Motivazione"],[["Qualità metodologica","30","26","24","Coerenza con gli obiettivi"],["Organizzazione","25","20","22","Presidio delle responsabilità"],["Esperienza proposta","20","17","16","Adeguatezza del gruppo"],["Accessibilità","15","12","13","Verifiche documentate"],["Migliorie","10","8","7","Misurabilità dei risultati"]],[135,35,60,60,203],merges=[(0,2,0,3)])
    scores.cell(0,2).text="Punteggi A / B"
    h(doc,"Osservazioni della commissione",2);para(doc,REPORT_PARAS[1]);para(doc,REPORT_PARAS[2])
    doc.add_page_break();h(doc,"Verifica documentale e conclusioni",1)
    for i,text in enumerate(("Completezza della proposta tecnica","Coerenza del calendario","Copertura delle responsabilità","Tracciabilità degli allegati","Verifica dei criteri di accettazione"),1):
        p=para(doc,f"{i}. {text}\tVERIFICATO",after=10);p.paragraph_format.tab_stops.add_tab_stop(Pt(493),WD_TAB_ALIGNMENT.RIGHT)
    for i in range(2):h(doc,f"Motivazione {i+1}",2);para(doc,REPORT_PARAS[i+2])
    p=para(doc,"Presidente\tComponente\tSegretario",before=22);p.paragraph_format.tab_stops.add_tab_stop(Pt(180));p.paragraph_format.tab_stops.add_tab_stop(Pt(360))
    para(doc,"Firme fittizie non autografe",size=8,color=MUTED)
    return doc


BUILDERS=[
    ("europass_fictitious","development",cv,["two-page CV","synthetic portrait","date tabs","hanging indents","genuine language table","header/footer","bullets"]),
    ("research_bulletin","development",research,["two columns","continuous sections","serif body","multipage","hierarchy"]),
    ("administrative_report","development",administration,["logo","right aligned date","recipient indentation","genuine evidence table","multipage"]),
    ("invoice_complex","development",invoice,["long authentic table","merged category cells","repeated table header","currency columns","multipage table"]),
    ("field_inspection","development",inspection,["floating picture","text beside picture","caption","genuine data table","multipage"]),
    ("mixed_orientation","development",mixed_orientation,["portrait-landscape-portrait","native sections","wide authentic matrix","multipage"]),
    ("typography_catalog","development",typography,["different font metrics","bold/italic/color","indentation","variable line spacing","multipage"]),
    ("financial_statement","holdout",statement,["independent financial layout","date and amount tabs","serif body","authentic data table","multipage"]),
    ("project_newsletter","holdout",newsletter,["unequal native columns","inline chart","column breaks","varying section widths","multipage"]),
    ("procurement_form","holdout",procurement,["administrative scoring form","aligned tabular fields","genuine merged score table","graphic paragraph borders","multipage"]),
]


def package_stats(doc):
    paragraphs=list(doc.paragraphs)
    cell_paragraphs=[];seen_cells=set()
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                if c._tc not in seen_cells:
                    seen_cells.add(c._tc);cell_paragraphs.extend(c.paragraphs)
    root=doc.element
    return {"expected_tables":len(doc.tables),"expected_images":len(list(root.iter(qn("pic:pic")))),
            "reference_body_paragraphs":len(paragraphs),"reference_table_cells":len(seen_cells),
            "reference_table_grid_cells":sum(len(row.cells) for t in doc.tables for row in t.rows),
            "reference_text":"\n".join(p.text for p in paragraphs+cell_paragraphs if p.text),
            "reference_textboxes":len(list(root.iter(qn("w:txbxContent"))))}


def generate(destination=DEFAULT_OUTPUT,renderer=None,only=None,render=True):
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    portrait=assets();documents=[]
    from pdf2docx_ai.quality.validator import find_renderer
    renderer=find_renderer(renderer) if render else renderer
    if render and not renderer:raise RuntimeError("LibreOffice not found; install it or pass --renderer explicitly")
    for identifier,split,builder,features in BUILDERS:
        if only and identifier not in only:continue
        doc=builder(portrait)
        source=destination/(identifier+".reference.docx");doc.save(source)
        stats=package_stats(doc)
        if stats["reference_textboxes"]:raise AssertionError("Text boxes forbidden in reference corpus")
        body_truth=destination/(identifier+".reference.txt");body_truth.write_text(stats.pop("reference_text"),encoding="utf-8")
        pdf=destination/(source.stem+".pdf")
        if render:
            with tempfile.TemporaryDirectory(prefix="complex-lo-",dir=destination) as profile:
                run=subprocess.run([renderer,"-env:UserInstallation="+Path(profile).as_uri(),"--headless","--convert-to","pdf","--outdir",str(destination),str(source)],capture_output=True,text=True,timeout=120)
            if run.returncode or not pdf.is_file():raise RuntimeError(f"Could not render {identifier}: {run.stderr} {run.stdout}")
            pdf_truth=destination/(identifier+".pdf.txt")
            if pymupdf is not None:
                with pymupdf.open(pdf) as parsed:
                    pages=len(parsed);sizes=[list(p.rect)[2:] for p in parsed]
                    text="\n".join(p.get_text(sort=True) for p in parsed)
            else:
                from pypdf import PdfReader
                parsed=PdfReader(pdf);pages=len(parsed.pages)
                sizes=[[float(p.mediabox.width),float(p.mediabox.height)] for p in parsed.pages]
                text="\n".join(p.extract_text() for p in parsed.pages)
            pdf_truth.write_text(text,encoding="utf-8")
        else:pages=None;sizes=[];pdf_truth=None
        documents.append({"id":identifier,"split":split,"reference_docx":str(source),"pdf":str(pdf),"ground_truth":str(pdf_truth) if pdf_truth else None,"reference_body_text":str(body_truth),"features":features,"pages":pages,"page_sizes_pt":sizes,"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),**stats})
        print(identifier,"pages=",pages,flush=True)
    manifest_path=destination/"manifest.json"
    if only and manifest_path.is_file():
        previous=json.loads(manifest_path.read_text())["documents"]
        documents.extend(d for d in previous if d["id"] not in set(only))
        order={b[0]:i for i,b in enumerate(BUILDERS)}
        documents.sort(key=lambda d:order[d["id"]])
    manifest={"schema_version":"1.0","description":"Complex realistic wholly fictional corpus. Reference DOCX authored independently, never converter output.","synthetic_only":True,"reference_uses_layout_tables":False,"reference_uses_textboxes":False,"renderer":renderer,"split_rule":"fixed seven development IDs and three held-out IDs; no tuning on held-out documents","documents":documents}
    (destination/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination",nargs="?",type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument("--renderer",type=str,default=None)
    parser.add_argument("--only",nargs="+",default=None)
    parser.add_argument("--no-render",action="store_true")
    args=parser.parse_args();generate(args.destination,args.renderer,args.only,not args.no_render)
