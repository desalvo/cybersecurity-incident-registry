'use strict';
// Login-only design preview. No network, cookies, storage or application changes.
const form=document.querySelector('#login-form');
const feedback=document.querySelector('#login-feedback');
function showFeedback(message,kind=''){
  feedback.textContent=message;
  feedback.className='feedback'+(kind?' '+kind:'');
  feedback.hidden=false;
}
form.addEventListener('submit',event=>{
  event.preventDefault();
  const valid=document.querySelector('#username').value.trim()==='demo'&&document.querySelector('#password').value==='cir-demo';
  if(!valid){showFeedback('Per questa anteprima usa demo / cir-demo. Non inserire credenziali reali.','error');return;}
  showFeedback('Accesso dimostrativo riuscito. Questa proposta riguarda soltanto la pagina di login.','success');
});
document.querySelector('#sso-button').addEventListener('click',()=>{
  showFeedback('Anteprima SSO: nell’applicazione si aprirà il provider configurato. Nessuna autenticazione esterna viene eseguita qui.');
});
