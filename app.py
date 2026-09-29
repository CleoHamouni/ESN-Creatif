import json
import re
from datetime import date, datetime
from html import escape

import streamlit as st

st.set_page_config(page_title="Manager de créatifs", page_icon="🎨", layout="wide")
st.markdown("""
<style>
.block-container{padding-top:1.5rem;padding-bottom:4rem}.hero{padding:25px;border-radius:18px;color:white;background:linear-gradient(135deg,#18354D,#25647A);margin-bottom:20px}.card{padding:16px;border:1px solid #DDE6EA;border-radius:14px;background:white;margin-bottom:12px}div[data-testid="stMetric"]{border:1px solid #DDE6EA;padding:14px;border-radius:12px;background:white}.stButton>button{background:#18A99A;color:white;border:none;font-weight:700}</style>
""", unsafe_allow_html=True)

PROFESSIONS=["Photographe","Vidéaste","Monteur vidéo","Pilote de drone","Graphiste","Motion designer","Directeur artistique","Community manager","Maquilleur / Maquilleuse","Styliste","Illustrateur / Illustratrice","Retoucheur / Retoucheuse","Sound designer","Ingénieur du son","Rédacteur / Rédactrice"]
BUDGET_MODES=["Le client a une enveloppe précise","Le client a une fourchette budgétaire","Le client attend notre estimation","Budget à confirmer"]
CRITERION_OPTIONS={
"Support / usage":["Usage interne","Site institutionnel","Réseaux sociaux organiques","Presse éditoriale","Édition commerciale","Affichage promotionnel","Campagne publicitaire","Packaging / merchandising"],
"Diffusion":["Moins de 1 000 exemplaires / vues","1 000 à 10 000","10 001 à 100 000","100 001 à 1 000 000","Plus de 1 000 000"],
"Territoire":["Local / régional","France","Europe","Monde"],
"Durée":["Opération ponctuelle, 3 mois maximum","Jusqu'à 1 an","Jusqu'à 3 ans","Plus de 3 ans"],
"Exclusivité":["Aucune exclusivité","Exclusivité limitée à un secteur","Exclusivité territoriale","Exclusivité totale"]}
COEFFICIENTS={"Support / usage":[.35,.70,.75,1,1.5,1.75,3,2.5],"Diffusion":[.5,1,2,4,8],"Territoire":[.7,1,1.75,3],"Durée":[.6,1,2,3.5],"Exclusivité":[1,2,3.5,6]}
IMPORTANCE_OPTIONS={"Livrable technique ou accessoire · 20 %":.20,"Création standard · 40 %":.40,"Création centrale · 60 %":.60,"Création à forte valeur commerciale · 80 %":.80,"Création signature ou stratégique · 100 %":1.00}
URGENCY_OPTIONS={"Planning normal · 0 %":0,"Délai resserré · 15 %":.15,"Urgent · 30 %":.30,"Très urgent · 50 %":.50,"Priorité absolue · 75 %":.75}
MINIMUM_RIGHTS=100.0

for k,v in {"briefs":[],"opportunities":[],"last_pricing":None,"last_context":{}}.items():
    if k not in st.session_state: st.session_state[k]=v

def euro(v): return f"{float(v or 0):,.2f} €".replace(","," ").replace(".",",")
def fmt_date(v): return v or "Non renseignée"
def budget_summary(b):
    m=b.get("budget_mode","Budget à confirmer")
    if m==BUDGET_MODES[0]: return f"{m} : {euro(b.get('budget_exact'))}"
    if m==BUDGET_MODES[1]: return f"{m} : {euro(b.get('budget_min'))} à {euro(b.get('budget_max'))}"
    return m

def auto_estimate(brief):
    """Abaque interne explicable, à valider humainement avant devis."""
    profiles=max(1,int(brief.get("profile_count",1) or 1))
    professions=brief.get("professions",[])
    deliverables=(brief.get("deliverables") or "").lower()
    project=(brief.get("project_type") or "").lower()
    prep=2.0+1.0*profiles
    production=6.0*profiles
    post=2.0*profiles
    if "vidéo" in project or "Vidéaste" in professions: production+=2*profiles; post+=4*profiles
    if "Monteur vidéo" in professions: post+=4*profiles
    if "Photographe" in professions: post+=2*profiles
    if "Motion designer" in professions: post+=6*profiles
    if "Graphiste" in professions or "Illustrateur / Illustratrice" in professions: production+=2*profiles; post+=2*profiles
    if any(x in deliverables for x in ["plusieurs","déclinaison","versions","série"]): post+=3
    if brief.get("multi_role_allowed")=="Oui" and len(professions)>1: production*=.9; post*=.9
    urgency_map={"Normal":"Planning normal · 0 %","Resserré":"Délai resserré · 15 %","Urgent":"Urgent · 30 %","Très urgent":"Très urgent · 50 %","À confirmer":"Planning normal · 0 %"}
    type_importance={"campagne":"Création à forte valeur commerciale · 80 %","photo":"Création centrale · 60 %","vidéo":"Création centrale · 60 %","graphisme":"Création centrale · 60 %","motion design":"Création centrale · 60 %","contenu social":"Création standard · 40 %","événement":"Création standard · 40 %"}
    assumptions=[f"{profiles} profil(s)",f"métiers : {', '.join(professions) if professions else 'non renseignés'}","pas de complexité technique exceptionnelle supposée","un cycle de validation standard supposé"]
    return {"preparation_hours":round(prep,1),"production_hours":round(production,1),"postproduction_hours":round(post,1),"preparation_rate":50.0,"production_rate":75.0,"postproduction_rate":60.0,"importance":type_importance.get(project,"Création centrale · 60 %"),"urgency":urgency_map.get(brief.get("urgency_known"),"Planning normal · 0 %"),"assumptions":assumptions}

def compute_price(ph,prh,poh,pr,rr,por,importance,urgency,selections,expenses,margin_pct,discount_pct):
    preparation=ph*pr; production=prh*rr; postproduction=poh*por; creative=preparation+production+postproduction
    base_rights=creative*IMPORTANCE_OPTIONS[importance]; urgency_amount=creative*URGENCY_OPTIONS[urgency]
    factor=1.0; details=[]
    for criterion,choice in selections.items():
        idx=CRITERION_OPTIONS[criterion].index(choice); coef=COEFFICIENTS[criterion][idx]; factor*=coef; details.append((criterion,choice,coef))
    calculated=base_rights*factor; rights=max(MINIMUM_RIGHTS,calculated) if base_rights else 0
    subtotal=creative+urgency_amount+rights+expenses; margin=subtotal*margin_pct/100; before=subtotal+margin; discount=before*discount_pct/100
    return {"preparation":preparation,"production":production,"postproduction":postproduction,"creative_cost":creative,"importance_label":importance,"urgency_label":urgency,"urgency_amount":urgency_amount,"base_rights":base_rights,"rights_factor":factor,"calculated_rights":calculated,"rights":rights,"minimum_applied":bool(base_rights and calculated<MINIMUM_RIGHTS),"expenses":expenses,"subtotal_before_margin":subtotal,"margin_pct":margin_pct,"margin_amount":margin,"discount_pct":discount_pct,"discount_amount":discount,"total":max(0,before-discount),"details":details}

def build_brief_prompt(b):
    jobs=", ".join(b.get("professions",[])) or "Non renseignés"
    return f"""Tu agis comme business manager de prestations créatives. À partir du brief ci-dessous, génère uniquement les questions encore nécessaires. Reste concis : 10 questions prioritaires maximum, puis 8 questions complémentaires maximum. N'invente aucune réponse.

BRIEF CONNU
- Client : {b.get('client') or 'Non renseigné'}
- Projet : {b.get('title') or 'Non renseigné'}
- Type : {b.get('project_type') or 'Non renseigné'}
- Nombre de profils : {b.get('profile_count') or 'Non renseigné'}
- Métiers : {jobs}
- Cumul de métiers possible : {b.get('multi_role_allowed') or 'Non renseigné'}
- Dates : démarrage {fmt_date(b.get('start_date'))}, production {fmt_date(b.get('production_date'))}, livraison {fmt_date(b.get('delivery_date'))}
- Lieu / modalité : {b.get('location') or 'Non renseigné'} / {b.get('work_mode') or 'Non renseigné'}
- Objectif : {b.get('business_goal') or 'Non renseigné'}
- Cible : {b.get('target_audience') or 'Non renseignée'}
- Message : {b.get('key_message') or 'Non renseigné'}
- Livrables : {b.get('deliverables') or 'Non renseignés'}
- Style / compétences : {b.get('skills') or 'Non renseignés'}
- Budget : {budget_summary(b)}
- Validation / retours : {b.get('approval_process') or 'Non renseigné'} / {b.get('revision_rounds') or 'Non renseigné'}
- Contraintes : {b.get('constraints') or 'Non renseignées'}
- Utilisations prévues : {b.get('usage_notes') or 'Non renseignées'}

PRIORITÉ ABSOLUE : OBTENIR LES DONNÉES DU SIMULATEUR
Les questions doivent permettre de renseigner précisément :
1. Heures de préparation : cadrage, repérage, script, storyboard, réunions, préparation matérielle.
2. Heures de production : présence, tournage, shooting, création, nombre de profils simultanés.
3. Heures de postproduction : tri, retouche, montage, étalonnage, son, sous-titrage, déclinaisons.
4. Importance du rendu : accessoire, standard, central, forte valeur commerciale ou signature.
5. Urgence : planning normal, resserré, urgent, très urgent ou priorité absolue.
6. Support exact : interne, site, réseaux organiques, presse, édition, affichage, publicité, packaging.
7. Diffusion : tirage, vues ou audience attendue.
8. Territoire : local, France, Europe ou monde.
9. Durée d'exploitation.
10. Exclusivité : aucune, sectorielle, territoriale ou totale.
11. Frais : matériel, studio, déplacements, hébergement, licences et achats externes.
12. Nombre de retours, fichiers sources, rushes et options.

TRAITEMENT DU BUDGET
Si le client attend notre estimation, ne lui demande pas un chiffre arbitraire. Pose les questions de périmètre ci-dessus et identifie les hypothèses de chiffrage. Si une enveloppe existe, vérifie ce qu'elle inclut.

FORMAT
A. 10 questions prioritaires maximum, formulées naturellement pour un rendez-vous client.
B. 8 questions complémentaires maximum.
C. Tableau « Donnée du simulateur | Réponse connue | Information manquante ».
D. Hypothèses provisoires nécessaires à une estimation automatique.
E. Points bloquants avant devis.
"""

def build_contract_prompt(ctx):
    p=ctx.get("pricing",{}); selections=ctx.get("selections",{}); lines="\n".join(f"- {k} : {v}" for k,v in selections.items())
    return f"""Tu agis comme assistant de revue contractuelle pour une prestation créative en France. Compare le contrat avec les paramètres ci-dessous. Cite les clauses pertinentes. Distingue faits, risques et recommandations. Cette analyse ne remplace pas un avis juridique.

PARAMÈTRES
- Importance : {ctx.get('importance')}
- Urgence : {ctx.get('urgency')}
- Préparation : {euro(p.get('preparation'))}
- Production : {euro(p.get('production'))}
- Postproduction : {euro(p.get('postproduction'))}
- Majoration urgence : {euro(p.get('urgency_amount'))}
- Base de droits : {euro(p.get('base_rights'))}
- Droits : {euro(p.get('rights'))}
- Frais : {euro(p.get('expenses'))}
- Marge : {euro(p.get('margin_amount'))}
- Total HT : {euro(p.get('total'))}

DROITS CONVENUS
{lines}

CONTRÔLE : parties, périmètre, profils, livrables, dates, retours, acceptation, prix, paiement, droits, adaptation, sous-licence, crédit, droit moral, droit à l'image, tiers, annulation, responsabilité, confidentialité, portfolio, sources, résiliation et juridiction.

FORMAT : résumé, tableau des écarts, clauses à négocier, rédactions correctives, questions avant signature et conclusion.

CONTRAT À ANALYSER
COLLER ICI LE CONTRAT
"""

def quote_html(client,project,p,notes,validity):
    rows="".join(f"<tr><td>{escape(c)}</td><td>{escape(v)}</td><td>{coef:.2f}</td></tr>" for c,v,coef in p["details"])
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'><style>body{{font-family:Arial;color:#21313D;margin:40px}}table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #CCD6DA;padding:9px}}th{{background:#18354A;color:white}}.total{{font-size:22px;font-weight:bold;color:#0B7E76}}</style></head><body><h1>DEVIS INDICATIF</h1><p><b>Client :</b> {escape(client)}<br><b>Projet :</b> {escape(project)}<br><b>Date :</b> {datetime.now().strftime('%d/%m/%Y')}<br><b>Validité :</b> {validity} jours</p><table><tr><th>Poste</th><th>Montant HT</th></tr><tr><td>Préparation</td><td>{euro(p['preparation'])}</td></tr><tr><td>Production</td><td>{euro(p['production'])}</td></tr><tr><td>Postproduction</td><td>{euro(p['postproduction'])}</td></tr><tr><td>Urgence</td><td>{euro(p['urgency_amount'])}</td></tr><tr><td>Droits</td><td>{euro(p['rights'])}</td></tr><tr><td>Frais</td><td>{euro(p['expenses'])}</td></tr><tr><td>Marge</td><td>{euro(p['margin_amount'])}</td></tr><tr><td>Remise</td><td>- {euro(p['discount_amount'])}</td></tr></table><p class='total'>Total HT : {euro(p['total'])}</p><h2>Paramètres des droits</h2><table><tr><th>Critère</th><th>Choix</th><th>Coefficient</th></tr>{rows}</table><h2>Notes</h2><p>{escape(notes).replace(chr(10),'<br>')}</p></body></html>"""

st.markdown("<div class='hero'><h1>🎨 Manager business de créatifs</h1><p>Qualification, estimation automatique, devis et sécurisation contractuelle.</p></div>",unsafe_allow_html=True)
tabs=st.tabs(["Briefs","Simulateur","Devis","Suivi","Analyse contrat IA","Sauvegarde"])

with tabs[0]:
    st.header("Briefs de mission")
    with st.form("brief_form",clear_on_submit=True):
        st.subheader("Identification et équipe")
        c1,c2,c3=st.columns(3)
        client=c1.text_input("Client *"); contact_name=c2.text_input("Contact principal"); contact_role=c3.text_input("Fonction du contact")
        title=c1.text_input("Nom du projet *"); project_type=c2.selectbox("Type de projet",["À préciser","Photo","Vidéo","Graphisme","Motion design","Contenu social","Événement","Campagne","Autre"]); profile_count=c3.number_input("Nombre de profils recherchés",min_value=1,value=1,step=1)
        professions=st.multiselect("Métier(s) nécessaires",PROFESSIONS); multi_role=st.radio("Un même profil peut-il couvrir plusieurs métiers ?",["Oui","Non","À confirmer"],horizontal=True)
        st.subheader("Dates et organisation")
        c1,c2,c3=st.columns(3); sk=c1.checkbox("Démarrage connu"); pk=c2.checkbox("Production connue"); dk=c3.checkbox("Livraison connue")
        start=c1.date_input("Démarrage",value=date.today()) if sk else None; prod_date=c2.date_input("Production",value=date.today()) if pk else None; delivery=c3.date_input("Livraison",value=date.today()) if dk else None
        c1,c2,c3=st.columns(3); location=c1.text_input("Lieu / zone"); work_mode=c2.selectbox("Modalité",["Sur site","À distance","Hybride","À confirmer"]); urgency_known=c3.selectbox("Urgence perçue",["Normal","Resserré","Urgent","Très urgent","À confirmer"])
        st.subheader("Besoin")
        business_goal=st.text_area("Objectif business ou communication"); target=st.text_area("Public cible"); message=st.text_area("Message principal / action attendue"); deliverables=st.text_area("Livrables déjà identifiés"); skills=st.text_area("Style, compétences, logiciels ou expérience"); references=st.text_area("Références et contre-exemples")
        st.subheader("Budget")
        budget_mode=st.selectbox("Situation budgétaire",BUDGET_MODES); c1,c2=st.columns(2); exact=minimum=maximum=0.0
        if budget_mode==BUDGET_MODES[0]: exact=c1.number_input("Enveloppe précise HT",min_value=0.0,step=100.0)
        elif budget_mode==BUDGET_MODES[1]: minimum=c1.number_input("Minimum HT",min_value=0.0,step=100.0); maximum=c2.number_input("Maximum HT",min_value=0.0,step=100.0)
        elif budget_mode==BUDGET_MODES[2]: st.info("L'outil produira une première estimation automatique à partir du brief et affichera ses hypothèses.")
        budget_includes=st.multiselect("Ce que le budget semble inclure",["Préparation","Production","Postproduction","Talents","Matériel","Déplacements","Droits","Marge","Taxes","Achat média","À confirmer"])
        st.subheader("Validation, contraintes et droits")
        c1,c2=st.columns(2); approval=c1.text_area("Décideur final et validation"); revisions=c2.selectbox("Allers-retours envisagés",["À confirmer","1","2","3","Plus de 3"]); constraints=c1.text_area("Contraintes techniques, légales, sécurité, RSE ou accessibilité"); client_inputs=c2.text_area("Éléments fournis par le client")
        usage=st.text_area("Utilisations, supports, diffusion, territoire, durée et exclusivité déjà envisagés"); description=st.text_area("Informations complémentaires")
        if st.form_submit_button("Créer le brief"):
            if not client or not title: st.error("Le client et le projet sont obligatoires.")
            elif budget_mode==BUDGET_MODES[1] and maximum and minimum>maximum: st.error("Le minimum dépasse le maximum.")
            else:
                st.session_state.briefs.append({"id":datetime.now().timestamp(),"client":client,"contact_name":contact_name,"contact_role":contact_role,"title":title,"project_type":project_type,"profile_count":int(profile_count),"professions":professions,"multi_role_allowed":multi_role,"start_date":start.isoformat() if start else None,"production_date":prod_date.isoformat() if prod_date else None,"delivery_date":delivery.isoformat() if delivery else None,"location":location,"work_mode":work_mode,"urgency_known":urgency_known,"business_goal":business_goal,"target_audience":target,"key_message":message,"deliverables":deliverables,"skills":skills,"references":references,"budget_mode":budget_mode,"budget_exact":exact,"budget_min":minimum,"budget_max":maximum,"budget_includes":budget_includes,"approval_process":approval,"revision_rounds":revisions,"constraints":constraints,"client_inputs":client_inputs,"usage_notes":usage,"description":description}); st.success("Brief créé.")
    if st.session_state.briefs:
        for i,b in enumerate(st.session_state.briefs):
            with st.expander(f"{b['client']} · {b['title']} · {b.get('profile_count',1)} profil(s)"):
                st.write("**Budget :**",budget_summary(b)); st.write("**Métiers :**",", ".join(b.get("professions",[])) or "Non renseignés"); st.write("**Dates :**",fmt_date(b.get("start_date")),"|",fmt_date(b.get("production_date")),"|",fmt_date(b.get("delivery_date")))
                if st.button("Supprimer",key=f"db{i}"): st.session_state.briefs.pop(i); st.rerun()
        st.divider(); st.subheader("Prompt IA de qualification ciblé")
        bi=st.selectbox("Brief à approfondir",range(len(st.session_state.briefs)),format_func=lambda i:f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}"); prompt=build_brief_prompt(st.session_state.briefs[bi]); st.text_area("Prompt prêt à copier",value=prompt,height=600); st.download_button("Télécharger le prompt",prompt,"prompt_qualification_brief.txt","text/plain")

with tabs[1]:
    st.header("Simulateur et estimation automatique")
    brief=None; estimate=None
    if st.session_state.briefs:
        bi=st.selectbox("Brief associé",range(len(st.session_state.briefs)),format_func=lambda i:f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}"); brief=st.session_state.briefs[bi]; estimate=auto_estimate(brief); use_auto=st.checkbox("Utiliser l'estimation automatique comme point de départ",value=True)
        st.info("Estimation indicative fondée sur un abaque interne. Elle doit être ajustée avec les réponses client.")
        with st.expander("Voir les hypothèses automatiques",expanded=True):
            st.write("Préparation :",estimate["preparation_hours"],"h | Production :",estimate["production_hours"],"h | Postproduction :",estimate["postproduction_hours"],"h"); st.write("Importance :",estimate["importance"],"| Urgence :",estimate["urgency"]); st.write("Hypothèses :"); [st.write("•",x) for x in estimate["assumptions"]]
    else: use_auto=False
    d=estimate if (estimate and use_auto) else {"preparation_hours":2.0,"production_hours":8.0,"postproduction_hours":3.0,"preparation_rate":50.0,"production_rate":75.0,"postproduction_rate":60.0,"importance":"Création centrale · 60 %","urgency":"Planning normal · 0 %"}
    st.subheader("Temps et taux")
    c1,c2,c3=st.columns(3); ph=c1.number_input("Heures de préparation",min_value=0.0,value=float(d["preparation_hours"]),step=.5,key=f"ph_{brief.get('id') if brief else 'x'}_{use_auto}"); prh=c2.number_input("Heures de production",min_value=0.0,value=float(d["production_hours"]),step=.5,key=f"prh_{brief.get('id') if brief else 'x'}_{use_auto}"); poh=c3.number_input("Heures de postproduction",min_value=0.0,value=float(d["postproduction_hours"]),step=.5,key=f"poh_{brief.get('id') if brief else 'x'}_{use_auto}")
    c1,c2,c3=st.columns(3); pr=c1.number_input("Tarif préparation / h HT",min_value=0.0,value=float(d["preparation_rate"]),step=10.0); rr=c2.number_input("Tarif production / h HT",min_value=0.0,value=float(d["production_rate"]),step=10.0); por=c3.number_input("Tarif postproduction / h HT",min_value=0.0,value=float(d["postproduction_rate"]),step=10.0)
    st.subheader("Valeur, urgence et droits"); importance=st.select_slider("Importance du rendu",options=list(IMPORTANCE_OPTIONS),value=d["importance"],key=f"imp_{brief.get('id') if brief else 'x'}_{use_auto}"); urgency=st.select_slider("Urgence",options=list(URGENCY_OPTIONS),value=d["urgency"],key=f"urg_{brief.get('id') if brief else 'x'}_{use_auto}")
    selections={}
    for criterion,options in CRITERION_OPTIONS.items(): selections[criterion]=st.select_slider(criterion,options=options,value=options[len(options)//2],key=f"{criterion}_{brief.get('id') if brief else 'x'}")
    st.subheader("Frais et ajustements"); c1,c2,c3=st.columns(3); expenses=c1.number_input("Frais HT",min_value=0.0,step=25.0); margin_pct=c2.number_input("Marge / honoraires %",min_value=0.0,max_value=100.0,value=10.0); discount_pct=c3.number_input("Remise %",min_value=0.0,max_value=100.0)
    p=compute_price(ph,prh,poh,pr,rr,por,importance,urgency,selections,expenses,margin_pct,discount_pct); st.session_state.last_pricing=p; st.session_state.last_context={"importance":importance,"urgency":urgency,"selections":selections,"pricing":p,"brief":brief}
    m1,m2,m3,m4,m5,m6=st.columns(6); m1.metric("Coût créatif",euro(p["creative_cost"])); m2.metric("Base droits",euro(p["base_rights"])); m3.metric("Urgence",euro(p["urgency_amount"])); m4.metric("Droits",euro(p["rights"])); m5.metric("Marge",euro(p["margin_amount"]),f"{p['margin_pct']:.0f} %"); m6.metric("Total HT",euro(p["total"]))
    st.markdown(f"<div class='card'><b>Marge</b><br>Assiette : {euro(p['subtotal_before_margin'])}<br>Taux : {p['margin_pct']:.0f} %<br><b>Montant : {euro(p['margin_amount'])}</b></div>",unsafe_allow_html=True)
    if brief:
        mode=brief.get("budget_mode")
        if mode==BUDGET_MODES[0] and brief.get("budget_exact"): gap=brief["budget_exact"]-p["total"]; st.success(f"Sous budget de {euro(gap)}") if gap>=0 else st.error(f"Dépassement de {euro(abs(gap))}")
        elif mode==BUDGET_MODES[1] and brief.get("budget_max"): st.success("Dans la fourchette client.") if brief.get("budget_min",0)<=p["total"]<=brief["budget_max"] else st.warning("Estimation hors fourchette client.")
        elif mode==BUDGET_MODES[2]: st.info("Cette estimation constitue un premier scénario recommandé. Présente les hypothèses au client avant engagement.")
    if p["minimum_applied"]: st.info(f"Minimum de droits appliqué : {euro(MINIMUM_RIGHTS)}")

with tabs[2]:
    st.header("Devis"); p=st.session_state.last_pricing
    if not p: st.info("Calcule d'abord une estimation.")
    else:
        b=st.session_state.last_context.get("brief") or {}; client=st.text_input("Client",value=b.get("client","")); project=st.text_input("Projet",value=b.get("title","")); validity=st.number_input("Validité jours",min_value=1,value=30); notes=st.text_area("Notes",value="Acompte, planning, livrables, retours et droits à confirmer."); html=quote_html(client,project,p,notes,validity); filename=re.sub(r"[^a-zA-Z0-9]+","_",project or "projet"); st.download_button("Télécharger le devis HTML",html.encode(),f"devis_{filename}.html","text/html")
with tabs[3]:
    st.header("Suivi")
    with st.form("opp",clear_on_submit=True):
        c1,c2,c3=st.columns(3); oc=c1.text_input("Client"); op=c2.text_input("Projet"); os=c3.selectbox("Statut",["À qualifier","Estimation à préparer","Devis envoyé","Relance","Gagné","Perdu"]); oa=c1.number_input("Montant HT",min_value=0.0); on=c2.text_input("Prochaine action"); note=c3.text_input("Notes")
        if st.form_submit_button("Ajouter"): st.session_state.opportunities.append({"client":oc,"project":op,"status":os,"amount":oa,"next_action":on,"notes":note})
    st.dataframe(st.session_state.opportunities,use_container_width=True,hide_index=True)
with tabs[4]:
    st.header("Analyse contrat IA")
    if not st.session_state.last_context: st.info("Effectue d'abord une simulation.")
    else: cp=build_contract_prompt(st.session_state.last_context); st.text_area("Prompt",value=cp,height=600); st.download_button("Télécharger",cp,"prompt_analyse_contrat.txt","text/plain")
with tabs[5]:
    st.header("Sauvegarde"); data={"version":7,"exported_at":datetime.now().isoformat(),"briefs":st.session_state.briefs,"opportunities":st.session_state.opportunities}; st.download_button("Télécharger JSON",json.dumps(data,ensure_ascii=False,indent=2),"manager_creatifs.json","application/json"); up=st.file_uploader("Restaurer JSON",type=["json"])
    if up and st.button("Restaurer"):
        try: d=json.loads(up.getvalue().decode("utf-8-sig")); st.session_state.briefs=d.get("briefs",[]); st.session_state.opportunities=d.get("opportunities",[]); st.rerun()
        except Exception as e: st.error(f"Fichier invalide : {e}")
