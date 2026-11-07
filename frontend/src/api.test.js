import {describe,it,expect,vi,beforeEach} from 'vitest';
import {api} from './api';
describe('API integration contract',()=>{
  beforeEach(()=>{sessionStorage.clear();vi.restoreAllMocks()});
  it('sends scoped authenticated JSON requests',async()=>{sessionStorage.setItem('auditflow-token','jwt');global.fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({items:[]})});await api('/rag/query',{method:'POST',body:{audit_id:2,query:'invoice'}});expect(fetch).toHaveBeenCalledWith('/api/rag/query',expect.objectContaining({headers:expect.objectContaining({Authorization:'Bearer jwt','Content-Type':'application/json'}),body:'{"audit_id":2,"query":"invoice"}'}))});
  it('keeps multipart uploads intact',async()=>{global.fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({items:[]})});const form=new FormData();form.append('audit_id','2');await api('/documents/upload',{method:'POST',body:form});expect(fetch.mock.calls[0][1].body).toBe(form);expect(fetch.mock.calls[0][1].headers['Content-Type']).toBeUndefined()});
  it('clears revoked sessions and exposes errors',async()=>{sessionStorage.setItem('auditflow-token','expired');global.fetch=vi.fn().mockResolvedValue({ok:false,status:401,json:async()=>({error:'Authentication required'})});await expect(api('/auth/me')).rejects.toThrow('Authentication required');expect(sessionStorage.getItem('auditflow-token')).toBeNull()});
  it.each(['/audits','/documents/1','/verification/run/2','/reconciliation/results/2','/agents/run/2','/reports/generate/2'])('propagates backend failures for %s',async path=>{global.fetch=vi.fn().mockResolvedValue({ok:false,status:403,json:async()=>({error:'Audit access denied'})});await expect(api(path)).rejects.toThrow('Audit access denied')});
});
