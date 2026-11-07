import React from 'react';
import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {BrowserRouter} from 'react-router-dom';
import {Shell} from './main';
import {api,download} from './api';
vi.mock('./api',()=>({api:vi.fn(),download:vi.fn().mockResolvedValue(undefined)}));
vi.mock('recharts',()=>({ResponsiveContainer:({children})=><div>{children}</div>,BarChart:()=>null,Bar:()=>null,XAxis:()=>null,YAxis:()=>null,Tooltip:()=>null,CartesianGrid:()=>null,PieChart:()=>null,Pie:()=>null,Cell:()=>null}));
const user={id:1,username:'Synthetic Auditor',role:'auditor'};
const audit={id:1,project_name:'Synthetic audit',status:'Under Review'};
function mockApi(path,options){
  if(path==='/auth/me')return Promise.resolve(user);
  if(path==='/auth/login')return Promise.resolve({user,token:'demo-jwt'});
  if(path.startsWith('/audits?'))return Promise.resolve({items:[audit],total:1});
  if(path==='/settings')return Promise.resolve({categories:['Purchase invoices','Bank statements']});
  if(path==='/dashboard/summary')return Promise.resolve({projects:1,documents:1,processed:1,pending:0,verified:2,discrepancies:1,requirements:3,complete:0,missing:1,categories:{},verification:{},uploads:{},audit_progress:[]});
  if(path.startsWith('/documents?'))return Promise.resolve({items:[{id:1,document_name:'invoice.csv',document_type:'Purchase invoices',file_version:1,processing_status:'Processed',created_at:'2026-03-01'}],total:1});
  if(path==='/documents/1')return Promise.resolve({id:1,document_name:'invoice.csv',document_type:'Purchase invoices',file_hash:'sourcehash',file_version:1,processing_status:'Processed',metadata_json:{malware_scan:'Not configured'}});
  if(path==='/documents/1/extracted-text')return Promise.resolve({chunks:[{id:1,chunk_text:'SYNTHETIC Atlas invoice 50000 INR',section_reference:'CSV row 2'}],records:[]});
  if(path==='/rag/query')return Promise.resolve({answer:'Matching source passages',sources:[{chunk_id:1,document_id:1,document_name:'invoice.csv',version:1,section_reference:'CSV row 2',text:'SYNTHETIC Atlas invoice 50000 INR',score:.8}],limitations:'Review required'});
  if(path==='/agents/run/1')return Promise.resolve({awaiting_review:true});
  if(path==='/reports/generate/1')return Promise.resolve({id:1,format:options.body.format});
  if(path==='/users')return Promise.resolve({items:[]});
  if(path==='/audits'&&options?.method==='POST')return Promise.resolve(audit);
  return Promise.resolve({items:[],total:0});
}
function mount(path){window.history.replaceState({},'',path);render(<BrowserRouter><Shell/></BrowserRouter>)}
beforeEach(()=>{sessionStorage.clear();sessionStorage.setItem('auditflow-token','jwt');sessionStorage.setItem('auditflow-audit','1');api.mockImplementation(mockApi);download.mockClear()});
afterEach(()=>{cleanup();vi.clearAllMocks()});
describe('Auditor interface workflows',()=>{
  it('logs in through the backend and renders database metrics',async()=>{sessionStorage.clear();mount('/');fireEvent.click(await screen.findByRole('button',{name:'Sign in to workspace'}));await screen.findByRole('heading',{name:'Audit overview'});expect(api).toHaveBeenCalledWith('/auth/login',expect.objectContaining({method:'POST'}));expect(sessionStorage.getItem('auditflow-token')).toBe('demo-jwt')});
  it('opens original document provenance and extracted text',async()=>{mount('/documents');fireEvent.click(await screen.findByRole('button',{name:/invoice.csv/}));await screen.findByRole('dialog',{name:'Evidence source viewer'});expect(await screen.findByText('sourcehash')).toBeTruthy();expect(screen.getByText('SYNTHETIC Atlas invoice 50000 INR')).toBeTruthy()});
  it('retrieves cited source passages for the active audit',async()=>{mount('/search');fireEvent.click(await screen.findByRole('button',{name:'Find purchase invoice INV-001'}));expect(await screen.findByText('SYNTHETIC Atlas invoice 50000 INR')).toBeTruthy();expect(api).toHaveBeenCalledWith('/rag/query',expect.objectContaining({body:expect.objectContaining({audit_id:1})}));expect(screen.getByRole('button',{name:/Doc #1/})).toBeTruthy()});
  it.each([['/verification','Run verification','/verification/run/1'],['/reconciliation','Run reconciliation','/reconciliation/run/1'],['/agents','Run audit workflow','/agents/run/1']])('runs %s against a scoped backend endpoint',async(path,label,endpoint)=>{mount(path);fireEvent.click(await screen.findByRole('button',{name:label}));await waitFor(()=>expect(api).toHaveBeenCalledWith(endpoint,{method:'POST'}))});
  it('generates a report snapshot before downloading it',async()=>{mount('/reports');fireEvent.click(await screen.findByRole('button',{name:'Generate PDF'}));await waitFor(()=>expect(download).toHaveBeenCalledWith('/reports/1/download','auditflow-report-1.pdf'));expect(api).toHaveBeenCalledWith('/reports/generate/1',{method:'POST',body:{format:'pdf'}})});
  it('exposes document upload with project scope and supported file types',async()=>{mount('/documents');fireEvent.click(await screen.findByRole('button',{name:'Upload documents'}));expect(screen.getByRole('dialog',{name:'Upload audit evidence'})).toBeTruthy();expect(screen.getByLabelText('Evidence files').accept).toContain('.csv')});
});
