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

# Ratios volontairement plus modérés, à ajuster après plusieurs devis réels.
COEFFICIENTS={
"Support / usage":[.25,.50,.60,.80,1.10,1.25,1.80,1.50],
"Diffusion":[.35,.70,1.20,2.20,4.00],
"Territoire":[.50,.85,1.25,2.00],
"Durée":[.45,.80,1.30,2.10],
"Exclusivité":[1.00,1.40,2.00,3.00]}
IMPORTANCE_OPTIONS={"Livrable technique ou accessoire · 15 %":.15,"Création standard · 30 %":.30,"Création centrale · 45 %":.45,"Création à forte valeur commerciale · 60 %":.60,"Création signature ou stratégique · 80 %":.80}
URGENCY_OPTIONS={"Planning normal · 0 %":0,"Délai resserré · 10 %":.10,"Urgent · 20 %":.20,"Très urgent · 35 %":.35,"Priorité absolue · 50 %":.50}
MINIMUM_RIGHTS=75.0

for key,default in {"briefs":[],"opportunities":[],"last_pricing":None,"last_context":{}}.items():
    if key not in st.session_state: st.session_state[key]=default

def euro(v): return f"{float(v or 0):,.2f} €".replace(","," ").replace(".",",")
def fmt_date(v):
    if not v:return "Non renseignée"
    try:return datetime.fromisoformat(v).strftime("%d/%m/%Y")
    except (TypeError,ValueError):return str(v)
def budget_summary(b):
    mode=b.get("budget_mode","Budget à confirmer")
    if mode==BUDGET_MODES[0]:return f"{mode} : {euro(b.get('budget_exact'))}"
    if mode==BUDGET_MODES[1]:return f"{mode} : {euro(b.get('budget_min'))} à {euro(b.get('budget_max'))}"
    return mode

def audience_to_diffusion(followers,views):
    audience=max(int(followers or 0),int(views or 0))
    if audience<1000:return CRITERION_OPTIONS["Diffusion"][0]
    if audience<=10000:return CRITERION_OPTIONS["Diffusion"][1]
    if audience<=100000:return CRITERION_OPTIONS["Diffusion"][2]
    if audience<=1000000:return CRITERION_OPTIONS["Diffusion"][3]
    return CRITERION_OPTIONS["Diffusion"][4]

def auto_estimate(b):
    profiles=max(1,int(b.get("profile_count",1) or 1));jobs=b.get("professions",[]);ptype=(b.get("project_type") or "").lower();deliverables=(b.get("deliverables") or "").lower();assumptions=[]
    prep=float(b.get("prep_hours_estimate",0) or 0);production=float(b.get("production_hours_estimate",0) or 0);post=float(b.get("post_hours_estimate",0) or 0)
    if prep==0:prep=2+profiles;assumptions.append("Préparation estimée par l'abaque interne.")
    if production==0:
        production=6*profiles
        if "vidéo" in ptype or "Vidéaste" in jobs:production+=2*profiles
        if "Graphiste" in jobs or "Illustrateur / Illustratrice" in jobs:production+=2*profiles
        assumptions.append("Production estimée selon les métiers et le nombre de profils.")
    if post==0:
        post=2*profiles
        if "Vidéaste" in jobs:post+=4*profiles
        if "Monteur vidéo" in jobs:post+=4*profiles
        if "Photographe" in jobs:post+=2*profiles
        if "Motion designer" in jobs:post+=6*profiles
        if any(x in deliverables for x in ["plusieurs","déclinaison","versions","série"]):post+=3
        assumptions.append("Postproduction estimée selon les métiers et les livrables.")
    if b.get("multi_role_allowed")=="Oui" and len(jobs)>1:production*=.9;post*=.9;assumptions.append("Réduction indicative liée au cumul de métiers.")
    diffusion=b.get("diffusion_criterion") or audience_to_diffusion(b.get("social_followers"),b.get("expected_views"))
    if not b.get("diffusion_criterion"):assumptions.append("Diffusion estimée depuis les abonnés ou les vues attendues.")
    return {"preparation_hours":round(prep,1),"production_hours":round(production,1),"postproduction_hours":round(post,1),"preparation_rate":50.,"production_rate":75.,"postproduction_rate":60.,"importance":b.get("importance_criterion") or "Création centrale · 45 %","urgency":b.get("urgency_criterion") or "Planning normal · 0 %","selections":{"Support / usage":b.get("support_criterion") or "Réseaux sociaux organiques","Diffusion":diffusion,"Territoire":b.get("territory_criterion") or "France","Durée":b.get("duration_criterion") or "Jusqu'à 1 an","Exclusivité":b.get("exclusivity_criterion") or "Aucune exclusivité"},"expenses":float(b.get("estimated_expenses",0) or 0),"assumptions":assumptions}

def compute_price(ph,prod_h,post_h,rprep,rprod,rpost,importance,urgency,selections,expenses,margin_pct,discount_pct):
    prep=ph*rprep;prod=prod_h*rprod;post=post_h*rpost;creative=prep+prod+post;base=creative*IMPORTANCE_OPTIONS[importance];urgent=creative*URGENCY_OPTIONS[urgency];factor=1.;details=[]
    for criterion,choice in selections.items():
        idx=CRITERION_OPTIONS[criterion].index(choice);coef=COEFFICIENTS[criterion][idx];factor*=coef;details.append((criterion,choice,coef))
    calculated=base*factor;rights=max(MINIMUM_RIGHTS,calculated) if base else 0;subtotal=creative+urgent+rights+expenses;margin=subtotal*margin_pct/100;before=subtotal+margin;discount=before*discount_pct/100
    return {"preparation":prep,"production":prod,"postproduction":post,"creative_cost":creative,"base_rights":base,"urgency_amount":urgent,"rights_factor":factor,"calculated_rights":calculated,"rights":rights,"minimum_applied":bool(base and calculated<MINIMUM_RIGHTS),"expenses":expenses,"subtotal_before_margin":subtotal,"margin_pct":margin_pct,"margin_amount":margin,"discount_pct":discount_pct,"discount_amount":discount,"total":max(0,before-discount),"details":details}

def external_prompt(b):
    jobs=", ".join(b.get("professions",[])) or "Non renseignés"
    return f"""Tu agis comme business manager de prestations créatives. À partir du brief ci-dessous, prépare uniquement les questions encore nécessaires à poser directement au client. Utilise « vous », reste neutre et professionnel.

RÈGLES
- Maximum 10 questions prioritaires et 6 complémentaires.
- Ne répète pas une information déjà renseignée.
- Il est normal que l'événement précède la date de rendu.
- Ne remets pas en cause le cumul de plusieurs métiers par un même talent.
- Si l'équipe doit être précisée, demande seulement si d'autres profils sont prévus et comment les séquences seront réparties.

BRIEF
- Client / projet : {b.get('client')} / {b.get('title')}
- Date de saisie : {fmt_date(b.get('brief_date'))}
- Événement : {fmt_date(b.get('event_date'))}
- Rendu : {fmt_date(b.get('delivery_date'))}
- Profils / métiers : {b.get('profile_count')} / {jobs}
- Objectif : {b.get('business_goal') or 'Non renseigné'}
- Cible : {b.get('target_audience') or 'Non renseignée'}
- Livrables : {b.get('deliverables') or 'Non renseignés'}
- Budget : {budget_summary(b)}
- Abonnés : {b.get('social_followers',0)}
- Vues attendues : {b.get('expected_views',0)}

SIMULATEUR
- Préparation : {b.get('prep_hours_estimate',0)} h
- Production : {b.get('production_hours_estimate',0)} h
- Postproduction : {b.get('post_hours_estimate',0)} h
- Importance : {b.get('importance_criterion') or 'Non renseignée'}
- Urgence : {b.get('urgency_criterion') or 'Non renseignée'}
- Support : {b.get('support_criterion') or 'Non renseigné'}
- Diffusion : {b.get('diffusion_criterion') or 'À estimer depuis l’audience'}
- Territoire : {b.get('territory_criterion') or 'Non renseigné'}
- Durée : {b.get('duration_criterion') or 'Non renseignée'}
- Exclusivité : {b.get('exclusivity_criterion') or 'Non renseignée'}
- Frais : {euro(b.get('estimated_expenses'))}

FORMAT
A. Questions prioritaires.
B. Questions complémentaires.
C. Tableau : Critère simulateur | Information connue | Question client.
D. Hypothèses provisoires séparées des questions.
E. Informations réellement bloquantes avant devis.
"""

def quote_html(client,project,p,notes,validity):
    rows="".join(f"<tr><td>{escape(c)}</td><td>{escape(v)}</td><td>{coef:.2f}</td></tr>" for c,v,coef in p["details"])
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'><style>body{{font-family:Arial;color:#21313D;margin:40px}}table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #CCD6DA;padding:9px}}th{{background:#18354A;color:white}}.total{{font-size:22px;font-weight:bold;color:#0B7E76}}</style></head><body><h1>DEVIS INDICATIF</h1><p><b>Client :</b> {escape(client)}<br><b>Projet :</b> {escape(project)}<br><b>Date :</b> {datetime.now().strftime('%d/%m/%Y')}<br><b>Validité :</b> {validity} jours</p><table><tr><th>Poste</th><th>Montant HT</th></tr><tr><td>Préparation</td><td>{euro(p['preparation'])}</td></tr><tr><td>Production</td><td>{euro(p['production'])}</td></tr><tr><td>Postproduction</td><td>{euro(p['postproduction'])}</td></tr><tr><td>Urgence</td><td>{euro(p['urgency_amount'])}</td></tr><tr><td>Droits</td><td>{euro(p['rights'])}</td></tr><tr><td>Frais</td><td>{euro(p['expenses'])}</td></tr><tr><td>Marge</td><td>{euro(p['margin_amount'])}</td></tr><tr><td>Remise</td><td>- {euro(p['discount_amount'])}</td></tr></table><p class='total'>Total HT : {euro(p['total'])}</p><h2>Droits</h2><table><tr><th>Critère</th><th>Choix</th><th>Coefficient</th></tr>{rows}</table><p>{escape(notes).replace(chr(10),'<br>')}</p></body></html>"""

st.markdown("<div class='hero'><h1>🎨 Manager business de créatifs</h1><p>Qualification, estimation, devis et prompt externe.</p></div>",unsafe_allow_html=True)
tabs=st.tabs(["Briefs","Simulateur","Devis","Suivi","Prompt IA externe","Sauvegarde"])

with tabs[0]:
    st.header("Brief de mission")
    with st.form("brief_form",clear_on_submit=True):
        c1,c2,c3=st.columns(3);brief_date=c1.date_input("Date de saisie",date.today(),format="DD/MM/YYYY");event_date=c2.date_input("Date de l'événement",date.today(),format="DD/MM/YYYY");delivery_date=c3.date_input("Date de rendu",date.today(),format="DD/MM/YYYY")
        c1,c2,c3=st.columns(3);client=c1.text_input("Client *");contact=c2.text_input("Contact principal");role=c3.text_input("Fonction");title=c1.text_input("Projet *");ptype=c2.selectbox("Type",["À préciser","Photo","Vidéo","Graphisme","Motion design","Contenu social","Événement","Campagne","Autre"]);profiles=c3.number_input("Nombre de profils",1,value=1)
        jobs=st.multiselect("Métiers nécessaires",PROFESSIONS);multi=st.radio("Un profil peut-il cumuler plusieurs métiers ?",["Oui","Non","À confirmer"],horizontal=True)
        c1,c2=st.columns(2);location=c1.text_input("Lieu / zone");work_mode=c2.selectbox("Modalité",["Sur site","À distance","Hybride","À confirmer"]);goal=c1.text_area("Objectif");target=c2.text_area("Public cible");message=c1.text_area("Message");deliverables=c2.text_area("Livrables");skills=c1.text_area("Style / compétences");references=c2.text_area("Références")
        st.subheader("Critères directs du simulateur")
        c1,c2,c3=st.columns(3);prep_h=c1.number_input("Heures préparation",0.,step=.5);production_h=c2.number_input("Heures production",0.,step=.5);post_h=c3.number_input("Heures postproduction",0.,step=.5)
        importance=c1.selectbox("Importance",["À confirmer"]+list(IMPORTANCE_OPTIONS));urgency=c2.selectbox("Urgence",["À confirmer"]+list(URGENCY_OPTIONS));support=c1.selectbox("Support",["À confirmer"]+CRITERION_OPTIONS["Support / usage"]);diffusion=c2.selectbox("Diffusion",["À estimer depuis l'audience"]+CRITERION_OPTIONS["Diffusion"])
        c1,c2,c3=st.columns(3);followers=c1.number_input("Abonnés",0,step=100);views=c2.number_input("Vues attendues",0,step=1000);paid_media=c3.number_input("Achat média HT",0.,step=100.)
        territory=c1.selectbox("Territoire",["À confirmer"]+CRITERION_OPTIONS["Territoire"]);duration=c2.selectbox("Durée",["À confirmer"]+CRITERION_OPTIONS["Durée"]);exclusivity=c3.selectbox("Exclusivité",["À confirmer"]+CRITERION_OPTIONS["Exclusivité"]);estimated_expenses=st.number_input("Frais estimés HT",0.,step=25.)
        budget_mode=st.selectbox("Situation budgétaire",BUDGET_MODES);c1,c2=st.columns(2);exact=minimum=maximum=0.
        if budget_mode==BUDGET_MODES[0]:exact=c1.number_input("Enveloppe HT",0.,step=100.)
        elif budget_mode==BUDGET_MODES[1]:minimum=c1.number_input("Minimum HT",0.,step=100.);maximum=c2.number_input("Maximum HT",0.,step=100.)
        approval=c1.text_area("Décideur et validation");revisions=c2.selectbox("Allers-retours",["À confirmer","1","2","3","Plus de 3"]);constraints=c1.text_area("Contraintes");inputs=c2.text_area("Éléments fournis");usage_notes=st.text_area("Droits et utilisations");description=st.text_area("Informations complémentaires")
        if st.form_submit_button("Créer le brief"):
            if not client or not title:st.error("Client et projet obligatoires.")
            elif delivery_date<event_date:st.error("La date de rendu ne peut pas précéder l'événement.")
            elif budget_mode==BUDGET_MODES[1] and maximum and minimum>maximum:st.error("Le minimum dépasse le maximum.")
            else:
                st.session_state.briefs.append({"id":datetime.now().timestamp(),"brief_date":brief_date.isoformat(),"event_date":event_date.isoformat(),"delivery_date":delivery_date.isoformat(),"client":client,"contact_name":contact,"contact_role":role,"title":title,"project_type":ptype,"profile_count":int(profiles),"professions":jobs,"multi_role_allowed":multi,"location":location,"work_mode":work_mode,"business_goal":goal,"target_audience":target,"key_message":message,"deliverables":deliverables,"skills":skills,"references":references,"prep_hours_estimate":prep_h,"production_hours_estimate":production_h,"post_hours_estimate":post_h,"importance_criterion":None if importance=="À confirmer" else importance,"urgency_criterion":None if urgency=="À confirmer" else urgency,"support_criterion":None if support=="À confirmer" else support,"diffusion_criterion":None if diffusion=="À estimer depuis l'audience" else diffusion,"social_followers":int(followers),"expected_views":int(views),"paid_media_budget":paid_media,"territory_criterion":None if territory=="À confirmer" else territory,"duration_criterion":None if duration=="À confirmer" else duration,"exclusivity_criterion":None if exclusivity=="À confirmer" else exclusivity,"estimated_expenses":estimated_expenses,"budget_mode":budget_mode,"budget_exact":exact,"budget_min":minimum,"budget_max":maximum,"approval_process":approval,"revision_rounds":revisions,"constraints":constraints,"client_inputs":inputs,"usage_notes":usage_notes,"description":description});st.success("Brief créé.")
    for i,b in enumerate(st.session_state.briefs):
        with st.expander(f"{b['client']} · {b['title']} · {fmt_date(b.get('event_date'))}"):
            st.write("**Rendu :**",fmt_date(b.get("delivery_date")));st.write("**Budget :**",budget_summary(b))
            if st.button("Supprimer",key=f"del_{i}"):st.session_state.briefs.pop(i);st.session_state.last_pricing=None;st.session_state.last_context={};st.rerun()

with tabs[1]:
    st.header("Simulateur")
    brief=None;estimate=None
    if st.session_state.briefs:
        idx=st.selectbox("Brief associé",range(len(st.session_state.briefs)),format_func=lambda i:f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}");brief=st.session_state.briefs[idx];estimate=auto_estimate(brief);use_auto=st.checkbox("Utiliser l'estimation automatique comme point de départ",True)
        with st.expander("Hypothèses",True):
            st.write(f"Préparation : {estimate['preparation_hours']} h | Production : {estimate['production_hours']} h | Postproduction : {estimate['postproduction_hours']} h")
            for assumption in estimate["assumptions"]:st.write("•",assumption)
    else:use_auto=False
    default=estimate if estimate and use_auto else {"preparation_hours":2.,"production_hours":8.,"postproduction_hours":3.,"preparation_rate":50.,"production_rate":75.,"postproduction_rate":60.,"importance":"Création centrale · 45 %","urgency":"Planning normal · 0 %","selections":{k:v[len(v)//2] for k,v in CRITERION_OPTIONS.items()},"expenses":0.}
    wk=f"{brief.get('id') if brief else 'manual'}_{use_auto}";c1,c2,c3=st.columns(3);ph=c1.number_input("Heures préparation",0.,value=float(default["preparation_hours"]),step=.5,key="ph_"+wk);prodh=c2.number_input("Heures production",0.,value=float(default["production_hours"]),step=.5,key="prod_"+wk);posth=c3.number_input("Heures postproduction",0.,value=float(default["postproduction_hours"]),step=.5,key="post_"+wk)
    c1,c2,c3=st.columns(3);rp=c1.number_input("Tarif préparation / h",0.,value=float(default["preparation_rate"]));rprod=c2.number_input("Tarif production / h",0.,value=float(default["production_rate"]));rpost=c3.number_input("Tarif postproduction / h",0.,value=float(default["postproduction_rate"]));imp=st.select_slider("Importance",list(IMPORTANCE_OPTIONS),value=default["importance"],key="imp_"+wk);urg=st.select_slider("Urgence",list(URGENCY_OPTIONS),value=default["urgency"],key="urg_"+wk);selections={}
    for criterion,options in CRITERION_OPTIONS.items():selections[criterion]=st.select_slider(criterion,options,value=default["selections"][criterion],key=criterion+wk)
    c1,c2,c3=st.columns(3);expenses=c1.number_input("Frais HT",0.,value=float(default["expenses"]));margin=c2.number_input("Marge %",0.,100.,10.);discount=c3.number_input("Remise %",0.,100.,0.)
    pricing=compute_price(ph,prodh,posth,rp,rprod,rpost,imp,urg,selections,expenses,margin,discount);st.session_state.last_pricing=pricing;st.session_state.last_context={"brief":brief,"selections":selections}
    mc=st.columns(6);mv=[("Créatif",pricing["creative_cost"]),("Base droits",pricing["base_rights"]),("Urgence",pricing["urgency_amount"]),("Droits",pricing["rights"]),("Marge",pricing["margin_amount"]),("Total HT",pricing["total"])]
    for col,(label,value) in zip(mc,mv):col.metric(label,euro(value))
    st.markdown(f"<div class='card'><b>Marge</b><br>Assiette : {euro(pricing['subtotal_before_margin'])}<br>Taux : {pricing['margin_pct']:.0f} %<br><b>Montant : {euro(pricing['margin_amount'])}</b></div>",unsafe_allow_html=True)

with tabs[2]:
    st.header("Devis");p=st.session_state.last_pricing;ctx=st.session_state.last_context or {}
    if not p:st.info("Calcule d'abord une estimation.")
    else:
        b=ctx.get("brief") or {};client=st.text_input("Client",b.get("client",""),key="qclient");project=st.text_input("Projet",b.get("title",""),key="qproject");validity=st.number_input("Validité jours",1,365,30);notes=st.text_area("Notes","Acompte, dates, livrables, retours et droits à confirmer.");html=quote_html(client,project,p,notes,validity);filename=re.sub(r"[^a-zA-Z0-9]+","_",project or "projet");st.download_button("Télécharger devis HTML",html.encode("utf-8"),f"devis_{filename}.html","text/html")
with tabs[3]:
    st.header("Suivi")
    with st.form("opp",clear_on_submit=True):
        c1,c2,c3=st.columns(3);oc=c1.text_input("Client");op=c2.text_input("Projet");os=c3.selectbox("Statut",["À qualifier","Estimation","Devis envoyé","Relance","Gagné","Perdu"]);oa=c1.number_input("Montant HT",0.);on=c2.text_input("Prochaine action");note=c3.text_input("Notes")
        if st.form_submit_button("Ajouter"):st.session_state.opportunities.append({"client":oc,"project":op,"status":os,"amount":oa,"next_action":on,"notes":note})
    st.dataframe(st.session_state.opportunities,use_container_width=True,hide_index=True)
with tabs[4]:
    st.header("Prompt pour IA externe")
    if not st.session_state.briefs:st.info("Crée d'abord un brief.")
    else:
        pi=st.selectbox("Brief",range(len(st.session_state.briefs)),format_func=lambda i:f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}",key="pi");prompt=external_prompt(st.session_state.briefs[pi]);st.text_area("Prompt prêt à copier",prompt,height=650);st.download_button("Télécharger le prompt",prompt,"prompt_externe.txt","text/plain")
with tabs[5]:
    st.header("Sauvegarde");export={"version":10,"exported_at":datetime.now().isoformat(),"briefs":st.session_state.briefs,"opportunities":st.session_state.opportunities};st.download_button("Télécharger JSON",json.dumps(export,ensure_ascii=False,indent=2),"manager_creatifs.json","application/json");up=st.file_uploader("Restaurer JSON",type=["json"])
    if up and st.button("Restaurer"):
        try:data=json.loads(up.getvalue().decode("utf-8-sig"));st.session_state.briefs=data.get("briefs",[]);st.session_state.opportunities=data.get("opportunities",[]);st.session_state.last_pricing=None;st.session_state.last_context={};st.rerun()
        except (UnicodeDecodeError,json.JSONDecodeError,TypeError) as error:st.error(f"Fichier invalide : {error}")
