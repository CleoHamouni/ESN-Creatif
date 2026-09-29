import json
import re
from datetime import date, datetime
from html import escape

import streamlit as st

st.set_page_config(page_title="Manager de créatifs", page_icon="🎨", layout="wide")
st.markdown("""
<style>
.block-container{padding-top:1.5rem;padding-bottom:4rem}.hero{padding:25px;border-radius:18px;color:white;background:linear-gradient(135deg,#18354D,#25647A);margin-bottom:20px}.card{padding:16px;border:1px solid #DDE6EA;border-radius:14px;background:white;margin-bottom:12px}.hint{color:#65727A;font-size:13px}div[data-testid="stMetric"]{border:1px solid #DDE6EA;padding:14px;border-radius:12px;background:white}.stButton>button{background:#18A99A;color:white;border:none;font-weight:700}</style>
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
def fmt_date(v):
    if not v:return "Non renseignée"
    try:return datetime.fromisoformat(v).strftime("%d/%m/%Y")
    except:return str(v)
def budget_summary(b):
    m=b.get("budget_mode","Budget à confirmer")
    if m==BUDGET_MODES[0]:return f"{m} : {euro(b.get('budget_exact'))}"
    if m==BUDGET_MODES[1]:return f"{m} : {euro(b.get('budget_min'))} à {euro(b.get('budget_max'))}"
    return m

def audience_to_diffusion(followers,expected_views):
    audience=max(int(followers or 0),int(expected_views or 0))
    if audience<1000:return CRITERION_OPTIONS["Diffusion"][0]
    if audience<=10000:return CRITERION_OPTIONS["Diffusion"][1]
    if audience<=100000:return CRITERION_OPTIONS["Diffusion"][2]
    if audience<=1000000:return CRITERION_OPTIONS["Diffusion"][3]
    return CRITERION_OPTIONS["Diffusion"][4]

def auto_estimate(b):
    profiles=max(1,int(b.get("profile_count",1) or 1)); jobs=b.get("professions",[]); project=(b.get("project_type") or "").lower(); deliverables=(b.get("deliverables") or "").lower()
    prep=float(b.get("prep_hours_estimate",0) or 0); production=float(b.get("production_hours_estimate",0) or 0); post=float(b.get("post_hours_estimate",0) or 0)
    assumptions=[]
    if not prep: prep=2+profiles; assumptions.append("préparation estimée par l'abaque")
    if not production:
        production=6*profiles
        if "vidéo" in project or "Vidéaste" in jobs:production+=2*profiles
        if "Graphiste" in jobs or "Illustrateur / Illustratrice" in jobs:production+=2*profiles
        assumptions.append("production estimée selon le nombre de profils et les métiers")
    if not post:
        post=2*profiles
        if "Vidéaste" in jobs:post+=4*profiles
        if "Monteur vidéo" in jobs:post+=4*profiles
        if "Photographe" in jobs:post+=2*profiles
        if "Motion designer" in jobs:post+=6*profiles
        if any(x in deliverables for x in ["plusieurs","déclinaison","versions","série"]):post+=3
        assumptions.append("postproduction estimée selon les métiers et livrables")
    if b.get("multi_role_allowed")=="Oui" and len(jobs)>1:production*=.9;post*=.9;assumptions.append("réduction de charge liée au cumul de métiers")
    importance=b.get("importance_criterion") or "Création centrale · 60 %"; urgency=b.get("urgency_criterion") or "Planning normal · 0 %"
    selections={
      "Support / usage":b.get("support_criterion") or "Réseaux sociaux organiques",
      "Diffusion":b.get("diffusion_criterion") or audience_to_diffusion(b.get("social_followers"),b.get("expected_views")),
      "Territoire":b.get("territory_criterion") or "France",
      "Durée":b.get("duration_criterion") or "Jusqu'à 1 an",
      "Exclusivité":b.get("exclusivity_criterion") or "Aucune exclusivité"}
    assumptions+=(["diffusion estimée à partir des abonnés ou vues attendues"] if not b.get("diffusion_criterion") else [])
    return {"preparation_hours":round(prep,1),"production_hours":round(production,1),"postproduction_hours":round(post,1),"preparation_rate":50.0,"production_rate":75.0,"postproduction_rate":60.0,"importance":importance,"urgency":urgency,"selections":selections,"expenses":float(b.get("estimated_expenses",0) or 0),"assumptions":assumptions}

def compute_price(ph,prod_h,post_h,rprep,rprod,rpost,importance,urgency,selections,expenses,margin_pct,discount_pct):
    prep=ph*rprep;prod=prod_h*rprod;post=post_h*rpost;creative=prep+prod+post;base=creative*IMPORTANCE_OPTIONS[importance];urgent=creative*URGENCY_OPTIONS[urgency]
    factor=1.;details=[]
    for criterion,choice in selections.items():
        idx=CRITERION_OPTIONS[criterion].index(choice);coef=COEFFICIENTS[criterion][idx];factor*=coef;details.append((criterion,choice,coef))
    calculated=base*factor;rights=max(MINIMUM_RIGHTS,calculated) if base else 0;subtotal=creative+urgent+rights+expenses;margin=subtotal*margin_pct/100;before=subtotal+margin;discount=before*discount_pct/100
    return {"preparation":prep,"production":prod,"postproduction":post,"creative_cost":creative,"importance_label":importance,"urgency_label":urgency,"urgency_amount":urgent,"base_rights":base,"rights_factor":factor,"calculated_rights":calculated,"rights":rights,"minimum_applied":bool(base and calculated<MINIMUM_RIGHTS),"expenses":expenses,"subtotal_before_margin":subtotal,"margin_pct":margin_pct,"margin_amount":margin,"discount_pct":discount_pct,"discount_amount":discount,"total":max(0,before-discount),"details":details}

def brief_prompt(b):
    jobs=", ".join(b.get("professions",[])) or "Non renseignés"
    return f"""Tu agis comme business manager de prestations créatives. À partir du brief ci-dessous, pose uniquement les questions encore nécessaires. Maximum 10 questions prioritaires et 6 complémentaires. N'invente aucune réponse.

BRIEF
- Client / projet : {b.get('client')} / {b.get('title')}
- Date de saisie : {fmt_date(b.get('brief_date'))}
- Date de l'événement : {fmt_date(b.get('event_date'))}
- Date de rendu : {fmt_date(b.get('delivery_date'))}
- Profils / métiers : {b.get('profile_count')} / {jobs}
- Cumul de métiers : {b.get('multi_role_allowed')}
- Objectif / cible / message : {b.get('business_goal') or 'NC'} / {b.get('target_audience') or 'NC'} / {b.get('key_message') or 'NC'}
- Livrables : {b.get('deliverables') or 'NC'}
- Budget : {budget_summary(b)}
- Abonnés réseaux sociaux : {b.get('social_followers',0)}
- Vues attendues : {b.get('expected_views',0)}

CRITÈRES DU SIMULATEUR DÉJÀ SAISIS
- Préparation : {b.get('prep_hours_estimate',0)} h
- Production : {b.get('production_hours_estimate',0)} h
- Postproduction : {b.get('post_hours_estimate',0)} h
- Importance : {b.get('importance_criterion') or 'NC'}
- Urgence : {b.get('urgency_criterion') or 'NC'}
- Support : {b.get('support_criterion') or 'NC'}
- Diffusion : {b.get('diffusion_criterion') or 'NC'}
- Territoire : {b.get('territory_criterion') or 'NC'}
- Durée : {b.get('duration_criterion') or 'NC'}
- Exclusivité : {b.get('exclusivity_criterion') or 'NC'}
- Frais estimés : {euro(b.get('estimated_expenses'))}

PRIORITÉ
Complète d'abord les critères du simulateur encore inconnus : tâches de préparation, durée réelle de production, volume de postproduction, importance commerciale, urgence justifiée, supports, audience/tirage, territoire, durée, exclusivité, frais, retours et fichiers sources. Pour les réseaux sociaux, demande si le nombre d'abonnés correspond au compte de la marque, aux comptes partenaires ou à l'audience cumulée, et distingue abonnés, portée estimée et achat média.

FORMAT
A. 10 questions prioritaires maximum.
B. 6 questions complémentaires maximum.
C. Tableau « Critère simulateur | Réponse connue | À confirmer ».
D. Hypothèses utilisables pour l'estimation automatique.
E. Points bloquants avant devis.
"""

def contract_prompt(ctx):
    p=ctx.get("pricing",{});lines="\n".join(f"- {k} : {v}" for k,v in ctx.get("selections",{}).items());b=ctx.get("brief") or {}
    return f"""Tu agis comme assistant de revue contractuelle pour une prestation créative en France. Compare le contrat avec les paramètres ci-dessous, cite les clauses et distingue faits, risques et recommandations. Cette analyse ne remplace pas un avis juridique.

DATES : saisie {fmt_date(b.get('brief_date'))}, événement {fmt_date(b.get('event_date'))}, rendu {fmt_date(b.get('delivery_date'))}
AUDIENCE : {b.get('social_followers',0)} abonnés, {b.get('expected_views',0)} vues attendues
MONTANTS : préparation {euro(p.get('preparation'))}, production {euro(p.get('production'))}, postproduction {euro(p.get('postproduction'))}, urgence {euro(p.get('urgency_amount'))}, droits {euro(p.get('rights'))}, frais {euro(p.get('expenses'))}, marge {euro(p.get('margin_amount'))}, total {euro(p.get('total'))}
DROITS :
{lines}

Contrôle : parties, périmètre, profils, livrables, dates, retours, acceptation, prix, paiement, droits, audience, adaptation, sous-licence, crédit, droit moral, droit à l'image, tiers, annulation, responsabilité, confidentialité, portfolio, sources, résiliation et juridiction.

FORMAT : résumé, tableau des écarts, clauses à négocier, corrections, questions avant signature et conclusion.

CONTRAT À ANALYSER
COLLER ICI LE CONTRAT
"""

def quote_html(client,project,p,notes,validity):
    rows="".join(f"<tr><td>{escape(c)}</td><td>{escape(v)}</td><td>{coef:.2f}</td></tr>" for c,v,coef in p["details"])
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'><style>body{{font-family:Arial;color:#21313D;margin:40px}}table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #CCD6DA;padding:9px}}th{{background:#18354A;color:white}}.total{{font-size:22px;font-weight:bold;color:#0B7E76}}</style></head><body><h1>DEVIS INDICATIF</h1><p><b>Client :</b> {escape(client)}<br><b>Projet :</b> {escape(project)}<br><b>Date :</b> {datetime.now().strftime('%d/%m/%Y')}<br><b>Validité :</b> {validity} jours</p><table><tr><th>Poste</th><th>Montant HT</th></tr><tr><td>Préparation</td><td>{euro(p['preparation'])}</td></tr><tr><td>Production</td><td>{euro(p['production'])}</td></tr><tr><td>Postproduction</td><td>{euro(p['postproduction'])}</td></tr><tr><td>Urgence</td><td>{euro(p['urgency_amount'])}</td></tr><tr><td>Droits</td><td>{euro(p['rights'])}</td></tr><tr><td>Frais</td><td>{euro(p['expenses'])}</td></tr><tr><td>Marge</td><td>{euro(p['margin_amount'])}</td></tr><tr><td>Remise</td><td>- {euro(p['discount_amount'])}</td></tr></table><p class='total'>Total HT : {euro(p['total'])}</p><h2>Droits</h2><table><tr><th>Critère</th><th>Choix</th><th>Coefficient</th></tr>{rows}</table><p>{escape(notes).replace(chr(10),'<br>')}</p></body></html>"""

st.markdown("<div class='hero'><h1>🎨 Manager business de créatifs</h1><p>Qualification détaillée, estimation automatique, devis et contrat.</p></div>",unsafe_allow_html=True)
tabs=st.tabs(["Briefs","Simulateur","Devis","Suivi","Analyse contrat IA","Sauvegarde"])

with tabs[0]:
    st.header("Brief de mission")
    with st.form("brief_form",clear_on_submit=True):
        st.subheader("1. Repères et dates")
        c1,c2,c3=st.columns(3);brief_date=c1.date_input("Date du jour / date de saisie",value=date.today(),format="DD/MM/YYYY");event_known=c2.checkbox("Date de l'événement connue");render_known=c3.checkbox("Date de rendu connue")
        event_date=c2.date_input("Date de l'événement",value=date.today(),format="DD/MM/YYYY") if event_known else None;delivery_date=c3.date_input("Date de rendu",value=date.today(),format="DD/MM/YYYY") if render_known else None
        c1,c2,c3=st.columns(3);client=c1.text_input("Client *");contact=c2.text_input("Contact principal");role=c3.text_input("Fonction du contact");title=c1.text_input("Projet *");project_type=c2.selectbox("Type",["À préciser","Photo","Vidéo","Graphisme","Motion design","Contenu social","Événement","Campagne","Autre"]);profiles=c3.number_input("Nombre de profils",min_value=1,value=1,step=1)
        jobs=st.multiselect("Métiers nécessaires",PROFESSIONS);multi=st.radio("Un profil peut-il cumuler plusieurs métiers ?",["Oui","Non","À confirmer"],horizontal=True)
        st.subheader("2. Besoin")
        c1,c2=st.columns(2);location=c1.text_input("Lieu / zone");work_mode=c2.selectbox("Modalité",["Sur site","À distance","Hybride","À confirmer"]);goal=c1.text_area("Objectif business / communication");target=c2.text_area("Public cible");message=c1.text_area("Message / action attendue");deliverables=c2.text_area("Livrables");skills=c1.text_area("Style, compétences, logiciels");references=c2.text_area("Références / contre-exemples")
        st.subheader("3. Critères directs du simulateur")
        st.caption("Chaque champ correspond directement à une donnée utilisée ou vérifiée dans le simulateur.")
        c1,c2,c3=st.columns(3);prep_hours=c1.number_input("Heures de préparation estimées",min_value=0.0,step=.5,help="Cadrage, réunions, repérage, script, storyboard, préparation matérielle");production_hours=c2.number_input("Heures de production estimées",min_value=0.0,step=.5,help="Tournage, shooting, création ou présence opérationnelle");post_hours=c3.number_input("Heures de postproduction estimées",min_value=0.0,step=.5,help="Tri, retouche, montage, son, sous-titrage, déclinaisons")
        importance=st.selectbox("Importance intrinsèque du rendu",["À confirmer"]+list(IMPORTANCE_OPTIONS));urgency=st.selectbox("Niveau d'urgence",["À confirmer"]+list(URGENCY_OPTIONS))
        c1,c2=st.columns(2);support=c1.selectbox("Support / usage",["À confirmer"]+CRITERION_OPTIONS["Support / usage"]);diffusion=c2.selectbox("Diffusion estimée",["À estimer depuis l'audience"]+CRITERION_OPTIONS["Diffusion"])
        c1,c2,c3=st.columns(3);followers=c1.number_input("Nombre d'abonnés sur les réseaux",min_value=0,step=100,help="Audience du compte principal ou audience cumulée à préciser");views=c2.number_input("Nombre de vues / portée attendue",min_value=0,step=1000);paid_media=c3.number_input("Budget d'achat média HT",min_value=0.0,step=100.0)
        c1,c2,c3=st.columns(3);territory=c1.selectbox("Territoire",["À confirmer"]+CRITERION_OPTIONS["Territoire"]);duration=c2.selectbox("Durée d'exploitation",["À confirmer"]+CRITERION_OPTIONS["Durée"]);exclusivity=c3.selectbox("Exclusivité",["À confirmer"]+CRITERION_OPTIONS["Exclusivité"])
        estimated_expenses=st.number_input("Frais déjà estimés HT",min_value=0.0,step=25.0,help="Matériel, studio, transport, hébergement, licences et achats externes")
        st.subheader("4. Budget, validation et risques")
        budget_mode=st.selectbox("Situation budgétaire",BUDGET_MODES);c1,c2=st.columns(2);exact=minimum=maximum=0.0
        if budget_mode==BUDGET_MODES[0]:exact=c1.number_input("Enveloppe précise HT",min_value=0.0,step=100.0)
        elif budget_mode==BUDGET_MODES[1]:minimum=c1.number_input("Minimum HT",min_value=0.0,step=100.0);maximum=c2.number_input("Maximum HT",min_value=0.0,step=100.0)
        budget_includes=st.multiselect("Éléments inclus dans le budget",["Préparation","Production","Postproduction","Talents","Matériel","Déplacements","Droits","Marge","Taxes","Achat média","À confirmer"])
        c1,c2=st.columns(2);approval=c1.text_area("Décideur final et validation");revisions=c2.selectbox("Allers-retours envisagés",["À confirmer","1","2","3","Plus de 3"]);constraints=c1.text_area("Contraintes techniques, légales, sécurité, RSE");inputs=c2.text_area("Éléments fournis par le client");usage_notes=st.text_area("Précisions sur les droits et utilisations");description=st.text_area("Informations complémentaires")
        if st.form_submit_button("Créer le brief"):
            if not client or not title:st.error("Client et projet obligatoires.")
            elif event_date and delivery_date and delivery_date<event_date:st.error("La date de rendu ne peut pas précéder l'événement.")
            elif budget_mode==BUDGET_MODES[1] and maximum and minimum>maximum:st.error("Le minimum dépasse le maximum.")
            else:
                st.session_state.briefs.append({"id":datetime.now().timestamp(),"brief_date":brief_date.isoformat(),"event_date":event_date.isoformat() if event_date else None,"delivery_date":delivery_date.isoformat() if delivery_date else None,"client":client,"contact_name":contact,"contact_role":role,"title":title,"project_type":project_type,"profile_count":int(profiles),"professions":jobs,"multi_role_allowed":multi,"location":location,"work_mode":work_mode,"business_goal":goal,"target_audience":target,"key_message":message,"deliverables":deliverables,"skills":skills,"references":references,"prep_hours_estimate":prep_hours,"production_hours_estimate":production_hours,"post_hours_estimate":post_hours,"importance_criterion":None if importance=="À confirmer" else importance,"urgency_criterion":None if urgency=="À confirmer" else urgency,"support_criterion":None if support=="À confirmer" else support,"diffusion_criterion":None if diffusion=="À estimer depuis l'audience" else diffusion,"social_followers":int(followers),"expected_views":int(views),"paid_media_budget":paid_media,"territory_criterion":None if territory=="À confirmer" else territory,"duration_criterion":None if duration=="À confirmer" else duration,"exclusivity_criterion":None if exclusivity=="À confirmer" else exclusivity,"estimated_expenses":estimated_expenses,"budget_mode":budget_mode,"budget_exact":exact,"budget_min":minimum,"budget_max":maximum,"budget_includes":budget_includes,"approval_process":approval,"revision_rounds":revisions,"constraints":constraints,"client_inputs":inputs,"usage_notes":usage_notes,"description":description});st.success("Brief créé.")
    if st.session_state.briefs:
        for i,b in enumerate(st.session_state.briefs):
            with st.expander(f"{b['client']} · {b['title']} · événement {fmt_date(b.get('event_date'))}"):
                st.write("**Saisie :**",fmt_date(b.get("brief_date")),"| **Rendu :**",fmt_date(b.get("delivery_date")));st.write("**Audience :**",b.get("social_followers",0),"abonnés |",b.get("expected_views",0),"vues attendues");st.write("**Budget :**",budget_summary(b))
                if st.button("Supprimer",key=f"del{i}"):st.session_state.briefs.pop(i);st.rerun()
        st.divider();idx=st.selectbox("Brief pour le prompt",range(len(st.session_state.briefs)),format_func=lambda i:f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}");prompt=brief_prompt(st.session_state.briefs[idx]);st.text_area("Prompt ciblé",value=prompt,height=600);st.download_button("Télécharger le prompt",prompt,"prompt_brief.txt","text/plain")

with tabs[1]:
    st.header("Simulateur et estimation automatique");brief=None;estimate=None
    if st.session_state.briefs:
        idx=st.selectbox("Brief associé",range(len(st.session_state.briefs)),format_func=lambda i:f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}");brief=st.session_state.briefs[idx];estimate=auto_estimate(brief);use_auto=st.checkbox("Utiliser les données du brief et l'estimation automatique",True)
        with st.expander("Hypothèses de l'estimation",True):st.write("Préparation",estimate["preparation_hours"],"h | Production",estimate["production_hours"],"h | Postproduction",estimate["postproduction_hours"],"h");[st.write("•",a) for a in estimate["assumptions"]]
    else:use_auto=False
    d=estimate if estimate and use_auto else {"preparation_hours":2.,"production_hours":8.,"postproduction_hours":3.,"preparation_rate":50.,"production_rate":75.,"postproduction_rate":60.,"importance":"Création centrale · 60 %","urgency":"Planning normal · 0 %","selections":{k:v[len(v)//2] for k,v in CRITERION_OPTIONS.items()},"expenses":0.}
    key=f"{brief.get('id') if brief else 'x'}_{use_auto}";c1,c2,c3=st.columns(3);ph=c1.number_input("Heures préparation",min_value=0.,value=float(d["preparation_hours"]),step=.5,key="ph"+key);prod_h=c2.number_input("Heures production",min_value=0.,value=float(d["production_hours"]),step=.5,key="prod"+key);post_h=c3.number_input("Heures postproduction",min_value=0.,value=float(d["postproduction_hours"]),step=.5,key="post"+key)
    c1,c2,c3=st.columns(3);rprep=c1.number_input("Tarif préparation / h",min_value=0.,value=float(d["preparation_rate"]));rprod=c2.number_input("Tarif production / h",min_value=0.,value=float(d["production_rate"]));rpost=c3.number_input("Tarif postproduction / h",min_value=0.,value=float(d["postproduction_rate"]))
    importance=st.select_slider("Importance",options=list(IMPORTANCE_OPTIONS),value=d["importance"],key="imp"+key);urgency=st.select_slider("Urgence",options=list(URGENCY_OPTIONS),value=d["urgency"],key="urg"+key);selections={}
    for criterion,options in CRITERION_OPTIONS.items():selections[criterion]=st.select_slider(criterion,options=options,value=d["selections"][criterion],key=criterion+key)
    c1,c2,c3=st.columns(3);expenses=c1.number_input("Frais HT",min_value=0.,value=float(d["expenses"]));margin_pct=c2.number_input("Marge %",min_value=0.,max_value=100.,value=10.);discount_pct=c3.number_input("Remise %",min_value=0.,max_value=100.,value=0.)
    p=compute_price(ph,prod_h,post_h,rprep,rprod,rpost,importance,urgency,selections,expenses,margin_pct,discount_pct);st.session_state.last_pricing=p;st.session_state.last_context={"pricing":p,"selections":selections,"importance":importance,"urgency":urgency,"brief":brief}
    cols=st.columns(6);labels=[("Créatif",p["creative_cost"]),("Base droits",p["base_rights"]),("Urgence",p["urgency_amount"]),("Droits",p["rights"]),("Marge",p["margin_amount"]),("Total HT",p["total"])];[cols[i].metric(label,euro(value)) for i,(label,value) in enumerate(labels)]
    st.markdown(f"<div class='card'><b>Marge</b><br>Assiette : {euro(p['subtotal_before_margin'])}<br>Taux : {p['margin_pct']:.0f} %<br><b>Montant : {euro(p['margin_amount'])}</b></div>",unsafe_allow_html=True)

with tabs[2]:
    st.header("Devis");p=st.session_state.last_pricing
    if not p:st.info("Calcule d'abord une estimation.")
    else:
        b=st.session_state.last_context.get("brief") or {};client=st.text_input("Client",value=b.get("client",""));project=st.text_input("Projet",value=b.get("title",""));validity=st.number_input("Validité jours",1,365,30);notes=st.text_area("Notes",value="Acompte, dates, livrables, retours et droits à confirmer.");html=quote_html(client,project,p,notes,validity);filename=re.sub(r"[^a-zA-Z0-9]+","_",project or "projet");st.download_button("Télécharger devis HTML",html.encode(),f"devis_{filename}.html","text/html")
with tabs[3]:
    st.header("Suivi")
    with st.form("opp",clear_on_submit=True):
        c1,c2,c3=st.columns(3);oc=c1.text_input("Client");op=c2.text_input("Projet");os=c3.selectbox("Statut",["À qualifier","Estimation","Devis envoyé","Relance","Gagné","Perdu"]);oa=c1.number_input("Montant HT",min_value=0.);on=c2.text_input("Prochaine action");note=c3.text_input("Notes")
        if st.form_submit_button("Ajouter"):st.session_state.opportunities.append({"client":oc,"project":op,"status":os,"amount":oa,"next_action":on,"notes":note})
    st.dataframe(st.session_state.opportunities,use_container_width=True,hide_index=True)
with tabs[4]:
    st.header("Analyse contrat IA")
    if not st.session_state.last_context:st.info("Effectue d'abord une simulation.")
    else:cp=contract_prompt(st.session_state.last_context);st.text_area("Prompt",value=cp,height=600);st.download_button("Télécharger",cp,"prompt_contrat.txt","text/plain")
with tabs[5]:
    st.header("Sauvegarde");data={"version":8,"exported_at":datetime.now().isoformat(),"briefs":st.session_state.briefs,"opportunities":st.session_state.opportunities};st.download_button("Télécharger JSON",json.dumps(data,ensure_ascii=False,indent=2),"manager_creatifs.json","application/json");up=st.file_uploader("Restaurer JSON",type=["json"])
    if up and st.button("Restaurer"):
        try:d=json.loads(up.getvalue().decode("utf-8-sig"));st.session_state.briefs=d.get("briefs",[]);st.session_state.opportunities=d.get("opportunities",[]);st.rerun()
        except Exception as e:st.error(f"Fichier invalide : {e}")
