"""Unit conversion is explicit; PDF points are 1/72 inch, mm are SI lengths."""
MM_PER_PT=25.4/72


def with_mm(values):
    return {**values,**{key[:-3]+'_mm':value*MM_PER_PT if value is not None else None
                       for key,value in values.items() if key.endswith('_pt') and (value is None or isinstance(value,(int,float)))}}
