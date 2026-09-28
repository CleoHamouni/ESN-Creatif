import io, json, re, uuid
from datetime import date, datetime, timedelta
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

st.set_page_config(page_title="ESN Artistique", page_icon="🎨", layout="wide")
st.markdown("""<style>.block-container{padding-top:1.5rem;padding-bottom:4rem}.hero{padding:26px;border-radius:18px;color:white;background:linear-gradient(135deg,#18354D,#25647A);margin-bottom:20px}.card{padding:16px;border:1px solid #DDE6EA;border-radius:14px;background:white;margin-bottom:12px}.score{color:#0B7E76;font-size:24px;font-weight:800}.muted{color:#65727A;font-size:14px}div[data-testid=stMetric]{border:1px solid #DDE6EA;padding:14px;border-radius:12px;background:white}.stButton>button{background:#18A99A;color:white;border:none;font-weight:700}</style>""", unsafe_allow_html=True)

for key, default in {"talents":[],"briefs":[],"quotes":[],"selected_quote":None}.items():
    if key not in st.session_state: st.session_state[key]=default

PROFESSIONS=[
    "Photographe", "Vidéaste", "Monteur vidéo", "Pilote de drone",
    "Graphiste", "Motion designer", "Directeur artistique",
    "Community manager", "Maquilleur / Maquilleuse", "Styliste",
    "Illustrateur / Illustratrice", "Retoucheur / Retoucheuse",
    "Sound designer", "Ingénieur du son", "Rédacteur / Rédactrice",
]

def as_list(value):
    """Compatibilité avec les anciennes sauvegardes où la profession était un texte."""
    if isinstance(value,list): return value
    if not value: return []
    return [x.strip() for x in str(value).split(",") if x.strip()]

# Coefficients internes de simulation. Ils sont modifiables et ne sont pas des barèmes officiels.
SUPPORT={"Usage interne":0.35,"Site institutionnel / réseaux organiques":0.70,"Édition commerciale":1.25,"Affichage promotionnel":1.10,"Campagne publicitaire":1.80,"Packaging / merchandising":1.60}
DIFFUSION={"Moins de 1 000 exemplaires / vues":0.60,"1 000 à 10 000":0.85,"10 001 à 100 000":1.10,"100 001 à 1 000 000":1.45,"Plus de 1 000 000":1.90}
TERRITORY={"Local / régional":0.70,"France":1.00,"Europe":1.30,"Monde":1.65}
DURATION={"Opération ponctuelle, 3 mois maximum":0.60,"Jusqu'à 1 an":1.00,"Jusqu'à 3 ans":1.35,"Plus de 3 ans":1.75}
EXCLUSIVITY={"Aucune exclusivité":1.00,"Exclusivité limitée à un secteur":1.25,"Exclusivité territoriale":1.45,"Exclusivité totale":1.90}

def euro(v): return f"{v:,.2f} €".replace(","," ")
def tok(v): return {x for x in re.split(r"[^a-zA-ZÀ-ÿ0-9]+",(v or "").lower()) if len(x)>1}

def match(t,b):
    talent_professions=set(as_list(t.get("professions",t.get("profession",[]))))
    needed_professions=set(as_list(b.get("professions",[])))
    overlap=talent_professions & needed_professions
    # Règle bloquante : sans métier commun, le talent est exclu du matching.
    if not overlap:
        return None,["Aucune profession commune."],["Profil exclu du matching métier."]

    score=60
    reasons=["Profession compatible : "+", ".join(sorted(overlap))+"."]
    gaps=[]
    wanted=tok(b.get("styles")); style_overlap=wanted & tok(t.get("styles"))
    if wanted:
        score+=round(20*len(style_overlap)/len(wanted))
        if style_overlap: reasons.append("Univers compatible : "+", ".join(sorted(style_overlap))+".")
        else: gaps.append("Adéquation artistique à challenger.")
    else:
        score+=5; reasons.append("Direction artistique encore ouverte.")
    bl=b.get("location","").lower().strip(); tl=t.get("location","").lower().strip()
    if bl and tl:
        if bl in tl or tl in bl: score+=10; reasons.append("Zone géographique compatible.")
        else: gaps.append("Déplacement à confirmer.")
    if t.get("availability","").lower()!="indisponible": score+=5; reasons.append("Disponibilité potentielle.")
    else: gaps.append("Talent déclaré indisponible.")
    return min(score,100),reasons,gaps

def shortlist(b,limit=5):
    out=[]
    for t in st.session_state.talents:
        score,reasons,gaps=match(t,b)
        if score is None:
            continue
        out.append({**t,"match_score":score,"reasons":reasons,"gaps":gaps})
    return sorted(out,key=lambda x:x["match_score"],reverse=True)[:limit]

def pricing(t,prep_h,days,post_h,hour_rate,day_rate,base_rights,support,diffusion,territory,duration,exclusivity,urgency,tech,travel,options,discount):
    hour_rate=hour_rate or float(t.get("hourly_rate",0)); day_rate=day_rate or float(t.get("base_day_rate",0)); base_rights=base_rights or float(t.get("base_rights",0))
    prep=prep_h*hour_rate; prod=days*day_rate; post=post_h*hour_rate; production_subtotal=prep+prod+post; urgency_value=production_subtotal*urgency/100
    rights_multiplier=SUPPORT[support]*DIFFUSION[diffusion]*TERRITORY[territory]*DURATION[duration]*EXCLUSIVITY[exclusivity]
    rights=base_rights*rights_multiplier
    before=production_subtotal+urgency_value+rights+tech+travel+options; discount_value=before*discount/100; total=max(0,before-discount_value)
    return {"preparation":prep,"production":prod,"postproduction":post,"production_subtotal":production_subtotal,"urgency":urgency_value,"rights_base":base_rights,"rights_multiplier":rights_multiplier,"rights":rights,"technical_fees":tech,"travel_fees":travel,"other_options":options,"discount":discount_value,"total_ht":total}

def quote_pdf(q):
    buf=io.BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=16*mm,bottomMargin=16*mm)
    ss=getSampleStyleSheet(); title=ParagraphStyle("T",parent=ss["Title"],fontName="Helvetica-Bold",fontSize=22,textColor=colors.HexColor("#18354D"),alignment=TA_CENTER); right=ParagraphStyle("R",parent=ss["BodyText"],alignment=TA_RIGHT); small=ParagraphStyle("S",parent=ss["BodyText"],fontSize=8,leading=10)
    story=[Paragraph("DEVIS",title),Table([[Paragraph(f"<b>Émetteur</b><br/>{q['issuer']}<br/>{q['issuer_address']}<br/>{q['issuer_email']}",ss["BodyText"]),Paragraph(f"<b>Devis n°</b> {q['number']}<br/><b>Date</b> {q['date']}<br/><b>Validité</b> {q['valid_until']}",right)],[Paragraph(f"<b>Client</b><br/>{q['client']}<br/>{q['client_address']}<br/>{q['client_email']}",ss["BodyText"]),Paragraph(f"<b>Projet</b><br/>{q['project']}<br/><b>Talent</b><br/>{q['talent']}",right)]],colWidths=[87*mm,87*mm],style=TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#CBD5DA")),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#F3F7F8")),("PADDING",(0,0),(-1,-1),8)])),Spacer(1,10),Paragraph("Détail de la proposition",ss["Heading2"])]
    p=q["pricing"]; rows=[["Désignation","Montant HT"]]
    for label,key in [("Préparation et cadrage","preparation"),("Production / création","production"),("Postproduction","postproduction"),("Majoration urgence","urgency"),("Droits d’exploitation","rights"),("Frais techniques","technical_fees"),("Déplacements","travel_fees"),("Options complémentaires","other_options")]:
        if p[key]: rows.append([label,euro(p[key])])
    if p["discount"]: rows.append(["Remise commerciale","- "+euro(p["discount"])])
    rows.append(["TOTAL HT",euro(p["total_ht"])])
    story.append(Table(rows,colWidths=[125*mm,49*mm],repeatRows=1,style=TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#18354D")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#EAF6F4")),("ALIGN",(1,1),(1,-1),"RIGHT"),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#CBD5DA")),("PADDING",(0,0),(-1,-1),7)])))
    story += [Spacer(1,10),Paragraph("Périmètre des droits d’exploitation",ss["Heading2"]),Table([["Support",q["support"]],["Diffusion",q["diffusion"]],["Territoire",q["territory"]],["Durée",q["duration"]],["Exclusivité",q["exclusivity"]]],colWidths=[45*mm,129*mm],style=TableStyle([("BACKGROUND",(0,0),(0,-1),colors.HexColor("#F3F7F8")),("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#CBD5DA")),("PADDING",(0,0),(-1,-1),7)])),Spacer(1,8),Paragraph(f"<b>Livrables :</b> {q['deliverables'] or 'À préciser'}",ss["BodyText"]),Paragraph(f"<b>Conditions :</b> {q['conditions'] or 'À préciser'}",ss["BodyText"]),Spacer(1,10),Paragraph("Le prix des droits est une estimation commerciale interne. Les droits effectivement cédés doivent être décrits précisément et validés dans le devis ou le contrat. Ce document ne constitue pas un avis juridique ni un barème officiel.",small)]
    doc.build(story); return buf.getvalue()

st.markdown("""<div class="hero"><h1>🎨 ESN Artistique</h1><p>Vivier, briefs, matching, tarification par exploitation et devis PDF.</p></div>""",unsafe_allow_html=True)
tabs=st.tabs(["📊 Tableau de bord","👤 Talents","📝 Briefs","🎯 Matching & tarif","📄 Devis","💾 Sauvegarde"])

with tabs[0]:
    a,b,c=st.columns(3); a.metric("Talents",len(st.session_state.talents)); b.metric("Briefs",len(st.session_state.briefs)); c.metric("Devis",len(st.session_state.quotes))
    st.info("Le temps mesure l’effort de production. Les droits d’exploitation mesurent l’usage : support, diffusion, territoire, durée et exclusivité.")
    st.warning("Les coefficients sont des règles internes de simulation, pas des barèmes officiels.")

with tabs[1]:
    st.subheader("Ajouter un talent")
    with st.form("talent_form",clear_on_submit=True):
        c1,c2=st.columns(2)
        with c1:
            name=st.text_input("Nom *"); professions=st.multiselect("Professions *",PROFESSIONS,placeholder="Choisir une ou plusieurs professions"); styles=st.text_input("Univers artistiques"); skills=st.text_area("Compétences"); location=st.text_input("Zone géographique")
        with c2:
            day=st.number_input("Tarif de production par jour HT",min_value=0.0,step=50.0); hour=st.number_input("Tarif horaire préparation / postproduction HT",min_value=0.0,step=10.0); rights=st.number_input("Base de droits d’exploitation HT",min_value=0.0,step=50.0); availability=st.selectbox("Disponibilité",["Disponible","À confirmer","Partielle","Indisponible"]); portfolio=st.text_input("Lien portfolio")
        notes=st.text_area("Notes internes")
        if st.form_submit_button("Ajouter le talent"):
            if not name or not professions: st.error("Le nom et au moins une profession sont obligatoires.")
            else:
                st.session_state.talents.append({"id":str(uuid.uuid4()),"name":name,"professions":professions,"styles":styles,"skills":skills,"location":location,"base_day_rate":day,"hourly_rate":hour,"base_rights":rights,"availability":availability,"portfolio":portfolio,"notes":notes}); st.success("Talent ajouté.")
    st.divider()
    for i,t in enumerate(st.session_state.talents):
        with st.expander(f"{t['name']} · {', '.join(as_list(t.get('professions',t.get('profession',[]))))}"):
            st.write("**Professions :**",", ".join(as_list(t.get("professions",t.get("profession",[]))))); st.write("**Styles :**",t.get("styles") or "Non renseigné"); st.write("**Production / jour :**",euro(float(t.get("base_day_rate",0)))); st.write("**Préparation / heure :**",euro(float(t.get("hourly_rate",0)))); st.write("**Base droits :**",euro(float(t.get("base_rights",0))))
            if t.get("portfolio"): st.markdown(f"[Voir le portfolio]({t['portfolio']})")
            if st.button("Supprimer",key=f"dt{i}"): st.session_state.talents.pop(i); st.rerun()

with tabs[2]:
    st.subheader("Créer un brief")
    with st.form("brief_form",clear_on_submit=True):
        c1,c2=st.columns(2)
        with c1:
            client=st.text_input("Client *"); project=st.text_input("Projet *"); professions=st.multiselect("Professions recherchées *",PROFESSIONS,placeholder="Choisir une ou plusieurs professions"); styles=st.text_input("Univers souhaités"); location=st.text_input("Lieu / zone")
        with c2:
            contact=st.text_input("Contact client"); email=st.text_input("Email client"); address=st.text_area("Adresse client"); budget=st.number_input("Budget indicatif global HT",min_value=0.0,step=100.0); deadline=st.text_input("Échéance")
        deliverables=st.text_area("Livrables attendus"); notes=st.text_area("Notes")
        if st.form_submit_button("Enregistrer le brief"):
            if not client or not project or not professions: st.error("Le client, le projet et au moins une profession sont obligatoires.")
            else:
                st.session_state.briefs.append({"id":str(uuid.uuid4()),"client":client,"project":project,"professions":professions,"styles":styles,"location":location,"contact_name":contact,"contact_email":email,"client_address":address,"budget":budget,"deadline":deadline,"deliverables":deliverables,"notes":notes}); st.success("Brief enregistré.")
    st.divider()
    for i,b in enumerate(st.session_state.briefs):
        with st.expander(f"{b['client']} · {b['project']}"):
            st.write("**Métiers :**",b.get("professions") or "Non renseignés"); st.write("**Budget :**",euro(float(b.get("budget",0)))); st.write("**Livrables :**",b.get("deliverables") or "Non renseignés")
            if st.button("Supprimer",key=f"db{i}"): st.session_state.briefs.pop(i); st.rerun()

with tabs[3]:
    st.subheader("Matching puis tarification")
    if not st.session_state.talents or not st.session_state.briefs: st.info("Ajoute au moins un talent et un brief.")
    else:
        bm={f"{b['client']} · {b['project']}":b for b in st.session_state.briefs}; bl=st.selectbox("Brief",list(bm)); b=bm[bl]; matches=shortlist(b,min(5,len(st.session_state.talents)))
        tm={}
        if not matches:
            st.error("Aucun talent ne possède l’une des professions demandées. Aucun profil hors métier n’est proposé.")
            st.stop()
        for pos,t in enumerate(matches,1):
            label=f"{pos}. {t['name']} · {', '.join(as_list(t.get('professions',t.get('profession',[]))))} · {t['match_score']}/100"; tm[label]=t; st.markdown(f"<div class='card'><div class='score'>{label}</div><div class='muted'>{' | '.join(t['reasons'])}</div></div>",unsafe_allow_html=True)
        tl=st.selectbox("Talent retenu",list(tm)); t=tm[tl]
        st.markdown("### 1. Production")
        c1,c2,c3=st.columns(3)
        prep=c1.number_input("Heures de préparation",min_value=0.0,value=2.0,step=.5); days=c1.number_input("Jours de production",min_value=0.0,value=1.0,step=.5); post=c2.number_input("Heures de postproduction",min_value=0.0,value=3.0,step=.5); hour=c2.number_input("Tarif horaire HT",min_value=0.0,value=float(t.get("hourly_rate",0)),step=10.0); day=c3.number_input("Tarif jour HT",min_value=0.0,value=float(t.get("base_day_rate",0)),step=50.0); urgency=c3.number_input("Majoration urgence (%)",min_value=0.0,max_value=200.0,step=5.0)
        st.markdown("### 2. Droits d’exploitation")
        c1,c2=st.columns(2)
        base=c1.number_input("Base de droits HT",min_value=0.0,value=float(t.get("base_rights",0)),step=50.0); support=c1.selectbox("Support / usage",list(SUPPORT)); diffusion=c1.selectbox("Diffusion / tirage",list(DIFFUSION)); territory=c2.selectbox("Territoire",list(TERRITORY)); duration=c2.selectbox("Durée",list(DURATION)); exclusivity=c2.selectbox("Exclusivité",list(EXCLUSIVITY))
        st.markdown("### 3. Frais")
        c1,c2,c3,c4=st.columns(4); tech=c1.number_input("Frais techniques HT",min_value=0.0,step=50.0); travel=c2.number_input("Déplacements HT",min_value=0.0,step=50.0); options=c3.number_input("Options HT",min_value=0.0,step=50.0); discount=c4.number_input("Remise (%)",min_value=0.0,max_value=100.0,step=1.0)
        p=pricing(t,prep,days,post,hour,day,base,support,diffusion,territory,duration,exclusivity,urgency,tech,travel,options,discount)
        m1,m2,m3,m4=st.columns(4); m1.metric("Production",euro(p["production_subtotal"])); m2.metric("Droits",euro(p["rights"])); m3.metric("Coefficient droits",f"× {p['rights_multiplier']:.2f}"); m4.metric("Total HT",euro(p["total_ht"]))
        if b.get("budget",0):
            gap=float(b["budget"])-p["total_ht"]; st.success(f"Sous le budget de {euro(gap)}") if gap>=0 else st.error(f"Dépassement de {euro(abs(gap))}")
        if st.button("Préparer le devis avec ce tarif"):
            st.session_state.selected_quote={"brief":b,"talent":t,"pricing":p,"support":support,"diffusion":diffusion,"territory":territory,"duration":duration,"exclusivity":exclusivity}; st.success("Simulation transférée dans l’onglet Devis.")

with tabs[4]:
    st.subheader("Générer un devis PDF")
    q0=st.session_state.selected_quote
    if not q0: st.info("Effectue d’abord un matching puis prépare le devis.")
    else:
        b=q0["brief"]; t=q0["talent"]; p=q0["pricing"]
        with st.form("quote_form"):
            c1,c2=st.columns(2)
            with c1:
                issuer=st.text_input("Nom / société émettrice *"); issuer_address=st.text_area("Adresse émetteur"); issuer_email=st.text_input("Email émetteur"); number=st.text_input("Numéro du devis",value=f"DEV-{datetime.now():%Y%m%d}-{len(st.session_state.quotes)+1:03d}")
            with c2:
                client=st.text_input("Client",value=b.get("client","")); client_address=st.text_area("Adresse client",value=b.get("client_address","")); client_email=st.text_input("Email client",value=b.get("contact_email","")); qdate=st.date_input("Date",value=date.today()); valid=st.date_input("Valable jusqu'au",value=date.today()+timedelta(days=30))
            project=st.text_input("Projet",value=b.get("project","")); deliverables=st.text_area("Livrables",value=b.get("deliverables","")); conditions=st.text_area("Conditions",value="Acompte et calendrier à préciser. Toute exploitation non décrite fera l’objet d’un accord complémentaire.")
            st.write("**Talent :**",t["name"]," | **Total HT :**",euro(p["total_ht"]))
            if st.form_submit_button("Créer le devis PDF"):
                if not issuer: st.error("Le nom de l’émetteur est obligatoire.")
                else:
                    q={"id":str(uuid.uuid4()),"issuer":issuer,"issuer_address":issuer_address.replace("\n","<br/>"),"issuer_email":issuer_email,"number":number,"date":qdate.strftime("%d/%m/%Y"),"valid_until":valid.strftime("%d/%m/%Y"),"client":client,"client_address":client_address.replace("\n","<br/>"),"client_email":client_email,"project":project,"talent":t["name"],"deliverables":deliverables.replace("\n","<br/>"),"conditions":conditions.replace("\n","<br/>"),"support":q0["support"],"diffusion":q0["diffusion"],"territory":q0["territory"],"duration":q0["duration"],"exclusivity":q0["exclusivity"],"pricing":p}; q["pdf"]=quote_pdf(q); st.session_state.quotes.append(q); st.success("Devis généré.")
        for q in reversed(st.session_state.quotes):
            st.download_button(f"Télécharger {q['number']} · {q['client']} · {euro(q['pricing']['total_ht'])}",q["pdf"],f"{q['number']}.pdf","application/pdf",key=q["id"])

with tabs[5]:
    st.subheader("Sauvegarde JSON")
    export={"version":2,"exported_at":datetime.now().isoformat(),"talents":st.session_state.talents,"briefs":st.session_state.briefs}
    st.download_button("Télécharger la sauvegarde",json.dumps(export,ensure_ascii=False,indent=2),"esn_artistique_sauvegarde.json","application/json")
    uploaded=st.file_uploader("Importer une sauvegarde",type=["json"])
    if uploaded:
        try:
            data=json.loads(uploaded.getvalue().decode("utf-8-sig"))
            for talent in data.get("talents",[]): talent["professions"]=as_list(talent.get("professions",talent.get("profession",[])))
            for brief in data.get("briefs",[]): brief["professions"]=as_list(brief.get("professions",[]))
            st.write(f"Fichier reconnu : {len(data.get('talents',[]))} talent(s), {len(data.get('briefs',[]))} brief(s).")
            if st.button("Restaurer ces données"):
                st.session_state.talents=data.get("talents",[]); st.session_state.briefs=data.get("briefs",[]); st.session_state.selected_quote=None; st.session_state.quotes=[]; st.rerun()
        except (UnicodeDecodeError,json.JSONDecodeError,TypeError) as e: st.error(f"Sauvegarde invalide : {e}")
