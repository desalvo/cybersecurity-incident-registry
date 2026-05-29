"""Moduli di supporto per la scomposizione progressiva delle route.

Le route pubbliche restano registrate da ``app.routes`` per compatibilità con
test, plugin e import storici. Le nuove aree funzionali vengono isolate qui e
richiamate dal facade principale senza cambiare endpoint o permessi.
"""
