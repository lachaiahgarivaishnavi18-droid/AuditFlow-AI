"""Remove the automation bypass created by CLI curl for this new project only."""
import json,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
project=json.loads((root/'.vercel/project.json').read_text())
assert project['projectName']=='auditflow-ai'
auth=json.loads((Path.home()/'AppData/Roaming/com.vercel.cli/Data/auth.json').read_text())
headers={'Authorization':'Bearer '+auth['token'],'Content-Type':'application/json'}
suffix='?teamId='+project['orgId']
url='https://api.vercel.com/v9/projects/'+project['projectId']+suffix
with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=30) as response:data=json.load(response)
bypasses=data.get('protectionBypass') or {}
if len(bypasses)>1:raise RuntimeError('More than one bypass exists; do not modify other access')
if bypasses:
    secret=next(iter(bypasses))
    payload=json.dumps({'revoke':{'secret':secret,'regenerate':False}}).encode()
    url='https://api.vercel.com/v1/projects/'+project['projectId']+'/protection-bypass'+suffix
    with urllib.request.urlopen(urllib.request.Request(url,data=payload,headers=headers,method='PATCH'),timeout=30) as response:result=json.load(response)
    assert secret not in (result.get('protectionBypass') or {})
print('Temporary CLI verification bypass removed; default deployment protection preserved.')
