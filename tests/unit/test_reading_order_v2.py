from pdf2docx_ai.document.models import BBox, Page, Region, TextLine, TextSpan
from pdf2docx_ai.document.reading_order import order_regions


def region(text, x0, y0, x1, y1, kind="text"):
    return Region(page_number=1, kind=kind, text=text,
                  bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1))


def page(regions, width=600):
    return Page(number=1, width=width, height=800, classification="native",
                cropbox=BBox(x0=0, y0=0, x1=width, y1=800), regions=regions)


def test_existing_two_column_order_ignores_decoration_and_omitted_content():
    left = region("left", 50, 100, 270, 300)
    right = region("right", 320, 100, 550, 300)
    rule = region("", 0, 150, 600, 151, "graphic")
    photo = region("", 0, 200, 600, 400, "image")
    omitted = region("hidden OCR", 0, 110, 600, 700)
    omitted.metadata["omit_editable"] = True
    result = order_regions(page([right, rule, photo, omitted, left]))
    assert result.columns == 2
    assert [r.text for r in result.regions[:2]] == ["left", "right"]
    assert result.metadata["column_geometry"][0][0] == 50
    assert all(r.column == -1 for r in (rule, photo))


def test_off_center_gutter_preserves_unequal_columns():
    result = order_regions(page([region("wide", 235, 100, 550, 350),
                                 region("narrow", 50, 100, 210, 350)]))
    assert result.columns == 2
    geometry = result.metadata["column_geometry"]
    assert geometry[0][1] - geometry[0][0] < geometry[1][1] - geometry[1][0]
    assert [r.text for r in result.regions] == ["narrow", "wide"]


def test_three_native_columns_read_down_each_lane():
    regions = [region(str(i), start, 100, start + 140, 350)
               for i, start in enumerate((45, 225, 405))]
    result = order_regions(page(list(reversed(regions))))
    assert result.columns == 3
    assert [r.column for r in result.regions] == [0, 1, 2]
    assert [r.text for r in result.regions] == ["0", "1", "2"]


def test_date_and_short_label_lanes_stay_in_tab_flow():
    regions = []
    for n, y in enumerate((100, 180, 260)):
        regions.extend([region(f"202{n}", 50, y, 95, y + 11),
                        region("Description of responsibilities", 163, y, 545, y + 55)])
    result = order_regions(page(regions))
    assert result.columns == 1
    assert result.metadata["reading_order_mode"] == "tabs"
    assert all(r.column == 0 for r in result.regions)


def test_short_labels_above_a_spanning_abstract_remain_full_width():
    author = region("Author and edition", 50, 70, 292, 81)
    label = region("Abstract", 50, 90, 95, 101)
    abstract = region("Full width abstract", 50, 110, 550, 150)
    left = region("left article", 50, 170, 285, 500)
    right = region("right article", 310, 170, 550, 350)
    result = order_regions(page([author, label, abstract, left, right]))
    assert result.columns == 2
    assert [r.column for r in (author, label, abstract, left, right)] == [-1, -1, -1, 0, 1]


def test_full_width_table_separates_column_bands_without_reordering():
    regions = [region("left1", 50, 70, 280, 180), region("right1", 310, 70, 550, 180),
               region("table", 50, 200, 550, 280, "table"),
               region("left2", 50, 300, 280, 450), region("right2", 310, 300, 550, 450)]
    result = order_regions(page(list(reversed(regions))))
    assert [r.text for r in result.regions] == ["left1", "right1", "table", "left2", "right2"]
    assert result.regions[2].column == -1


def test_joined_measured_block_is_split_at_true_gutter():
    lines = []
    for x in (50, 235):
        for y in (100, 114, 128):
            b = BBox(x0=x, y0=y, x1=x + (155 if x == 50 else 310), y1=y + 11)
            span = TextSpan(text=f"{x}:{y}", bbox=b, size=11, baseline=(x, y + 9))
            lines.append(TextLine(text=span.text, bbox=b, baseline=span.baseline, spans=[span]))
    joined = region("joined", 50, 100, 545, 139)
    joined.lines = lines
    joined.spans = [s for l in lines for s in l.spans]
    result = order_regions(page([joined]))
    assert result.columns == 2
    assert len(result.regions) == 2
    assert [len(r.lines) for r in result.regions] == [3, 3]
    assert len({r.id for r in result.regions}) == 2
    assert sum(len(r.spans) for r in result.regions) == 6


def test_separate_native_blocks_on_one_baseline_become_one_tab_row():
    fragments=[]
    for text,x0,x1 in (("Invoice EX-27",50,130),("Date 21/11/2026",430,550)):
        r=region(text,x0,100,x1,112)
        span=TextSpan(text=text,bbox=r.bbox,size=11,baseline=(x0,110))
        r.spans=[span]
        r.lines=[TextLine(text=text,bbox=r.bbox,baseline=span.baseline,spans=[span])]
        fragments.append(r)
    result=order_regions(page(fragments))
    assert result.columns==1
    assert len(result.regions)==1
    assert result.regions[0].text=="Invoice EX-27\tDate 21/11/2026"
    assert len(result.regions[0].lines)==2
    # Reordering checkpoints is idempotent and does not duplicate text.
    assert order_regions(result).regions[0].text==result.regions[0].text
