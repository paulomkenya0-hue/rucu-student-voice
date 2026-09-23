fetch('/api/settings-public').then(r=>r.json()).then(s=>{
const ay=document.getElementById('ay'); if(ay) ay.textContent=s.academic_year||'2026/2027';
const ay2=document.getElementById('ay2'); if(ay2) ay2.textContent=s.academic_year||'2026/2027';
document.getElementById('foot-year').textContent=(s.university_name||'RUCU')+' · '+(s.academic_year||'');
}).catch(()=>{});
