"""Preserve previous reports and only explicitly supplied, verified artifacts."""
from pathlib import Path
import hashlib,json,shutil


def archive_existing(report,root,*,docx=None,pdf=None):
    report=Path(report)
    if not report.is_file():return None
    raw=report.read_bytes();identity=hashlib.sha256(raw).hexdigest();folder=Path(root)/'previous'/identity
    folder.mkdir(parents=True,exist_ok=True)
    saved=folder/'report.json'
    try:
        with saved.open('xb') as stream:stream.write(raw)
    except FileExistsError:pass
    try:data=json.loads(raw)
    except (ValueError,UnicodeDecodeError):return {'history_status':'unparseable_previous_report_preserved','archive':str(folder)}
    assessment=data.get('assessment',data);inputs=assessment.get('inputs',{});artifacts=[]
    for kind,provided,key in (('docx',docx,'docx_sha256'),('pdf',pdf,'rendered_pdf_sha256')):
        if provided is None:continue
        file=Path(provided)
        if not file.is_file():continue
        digest=hashlib.sha256(file.read_bytes()).hexdigest();expected=inputs.get(key)
        if expected and digest==expected:
            target=folder/('artifact.'+kind)
            if not target.exists():shutil.copy2(file,target)
            artifacts.append({'kind':kind,'status':'verified_saved','sha256':digest,'path':str(target)})
        else:artifacts.append({'kind':kind,'status':'not_saved_identity_unverified_or_changed','observed_sha256':digest,'expected_sha256':expected})
    metadata=folder/'provenance.json'
    try:
        with metadata.open('x') as stream:json.dump({'report_sha256':identity,'artifacts':artifacts,'policy':'No artifact path from report data is followed.'},stream,indent=2)
    except FileExistsError:pass
    return data
