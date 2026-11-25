# CIR 0.10.0-1 RC56 — documentazione didattica e screenshot ottimizzate

- Presentazione visuale: 77 slide in PPTX e PDF, da immagini browser autentiche del commit `919b027403ee55db05b2355cd2f8fbd09c7cf7b4`, build `20261124`, con dati esclusivamente sintetici.
- Le immagini nel PPTX locale sono conversioni JPEG (qualità 90) delle PNG originali dell'artefatto CI; il manifest originale non è stato modificato. Un registro con SHA-256 di sorgente e derivato ne permette la verifica.
- Le future catture CI saranno in JPEG qualità 90 e verranno validate, installate e incorporate senza ricodifica successiva. I manifest PNG storici rimangono compatibili.
- Tre nuove schermate obbligatorie sono state aggiunte alla fixture browser CI: mapping AcroForm, configurazione Alfresco e comandi Alfresco nella scheda incidente; **non sono ancora disponibili nel vecchio artefatto**. Fino al prossimo run, i punti relativi ai mapping e ad Alfresco nel PPTX visuale usano schemi chiaramente identificati, mai screenshot inventati.
- I loghi con trasparenza, gli schemi sorgente e le prime pagine dei manuali restano PNG.
- Il browser CI, la suite PostgreSQL e i gate production devono ancora essere eseguiti sul nuovo commit.
