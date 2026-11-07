export async function api(path,options={}) {
  const token=sessionStorage.getItem('auditflow-token');
  const headers={...(token?{Authorization:`Bearer ${token}`}:{})};
  if(options.body && !(options.body instanceof FormData)) {headers['Content-Type']='application/json';options={...options,body:JSON.stringify(options.body)};}
  const response=await fetch(`/api${path}`,{...options,headers:{...headers,...options.headers}});
  if(!response.ok){const data=await response.json().catch(()=>({error:'Server unavailable'}));if(response.status===401){sessionStorage.removeItem('auditflow-token');window.dispatchEvent(new Event('auth-expired'));}throw new Error(data.error+(data.details?' · '+data.details.map(d=>d.field+': '+d.message).join('; '):''));}
  return response.json();
}
export async function download(path,name){const response=await fetch(`/api${path}`,{headers:{Authorization:`Bearer ${sessionStorage.getItem('auditflow-token')}`}});if(!response.ok){const error=await response.json();throw new Error(error.error);}const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
