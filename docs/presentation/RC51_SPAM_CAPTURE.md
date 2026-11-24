# RC51 - acquisizione browser SPAM

La fixture di documentazione avvia CIR con SQLite isolato e dati sintetici, senza connessioni a sistemi di produzione. Importa i 13 step e le condizioni del workflow SPAM anonimizzato e acquisisce due nuove immagini autentiche dalla pagina incidente, con i pulsanti e le frecce effettivamente renderizzati.

La prova non invia notifiche, non firma documenti e non simula il completamento delle fasi. Gli screenshot devono essere acquisiti da Chromium nella CI e attestati con SHA, commit e build nel manifest. Non utilizzare immagini statiche o mock come evidenza del browser.

Le nuove immagini `spam-incident-desktop` e `spam-workflow-steps` sono richieste dal validatore dell'evidenza. La pubblicazione della presentazione definitiva dovra' usarle solo dopo acquisizione e validazione della stessa build.

## Esecuzione CI

Eseguire la CI completa, non `[ci-security]`. La fixture SPAM non deve usare il database reale. I manifest aggiornati includono `spam-incident-desktop` e `spam-workflow-steps`; il deck RC50 rimane provvisorio fino alla generazione delle catture e alla loro integrazione verificata nella presentazione.
