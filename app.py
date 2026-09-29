import json
import re
from datetime import datetime
from html import escape
import streamlit as st

st.set_page_config(page_title="ESN Artistique", page_icon="🎨", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.8rem; padding-bottom: 4rem;}
.main-title {padding: 24px; border-radius: 18px; color: white; background: linear-gradient(135deg,#18354D,#25647A); margin-bottom: 18px;}
.card {padding: 16px; border: 1px solid #DDE6EA; border-radius: 14px; background: white; margin-bottom: 12px;}
.score {color:#0B7E76; font-size:25px; font-weight:800;}
.small {color:#65727A; font-size:14px;}
div[data-testid="stMetric"] {border:1px solid #DDE6EA; padding:14px; border-radius:12px; background:white;}
.stButton > button {background:#18A99A; color:white; border:none; font-weight:700;}
</style>
""", unsafe_allow_html=True)

PROFESSIONS = [
    "Photographe", "Vidéaste", "Monteur vidéo", "Pilote de drone",
    "Graphiste", "Motion designer", "Directeur artistique",
    "Community manager", "Maquilleur / Maquilleuse", "Styliste",
    "Illustrateur / Illustratrice", "Retoucheur / Retoucheuse",
    "Sound designer", "Ingénieur du son", "Rédacteur / Rédactrice",
]
CRITERION_OPTIONS = {
    "Support / usage": ["Usage interne", "Site institutionnel", "Réseaux sociaux organiques", "Presse éditoriale", "Édition commerciale", "Affichage promotionnel", "Campagne publicitaire", "Packaging / merchandising"],
    "Diffusion": ["Moins de 1 000 exemplaires / vues", "1 000 à 10 000", "10 001 à 100 000", "100 001 à 1 000 000", "Plus de 1 000 000"],
    "Territoire": ["Local / régional", "France", "Europe", "Monde"],
    "Durée": ["Opération ponctuelle, 3 mois maximum", "Jusqu'à 1 an", "Jusqu'à 3 ans", "Plus de 3 ans"],
    "Exclusivité": ["Aucune exclusivité", "Exclusivité limitée à un secteur", "Exclusivité territoriale", "Exclusivité totale"],
}
DEFAULT_COEFFICIENTS = {
    "Support / usage": [0.35, 0.70, 0.75, 1.00, 1.50, 1.75, 3.00, 2.50],
    "Diffusion": [0.50, 1.00, 2.00, 4.00, 8.00],
    "Territoire": [0.70, 1.00, 1.75, 3.00],
    "Durée": [0.60, 1.00, 2.00, 3.50],
    "Exclusivité": [1.00, 2.00, 3.50, 6.00],
}

def init_state():
    defaults = {
        "talents": [], "briefs": [], "opportunities": [],
        "coefficients": DEFAULT_COEFFICIENTS.copy(),
        "last_pricing": None, "last_matches": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
init_state()

def norm_set(value):
    if isinstance(value, list):
        return {str(x).strip().lower() for x in value if str(x).strip()}
    if not value:
        return set()
    return {x for x in re.split(r"[^a-zA-ZÀ-ÿ0-9/]+", str(value).lower()) if len(x) > 1}

def calculate_match(talent, brief):
    wanted = norm_set(brief.get("professions", []))
    offered = norm_set(talent.get("professions", []))
    common = wanted & offered
    if not common:
        return None
    score = 60.0
    reasons = ["Profession compatible : " + ", ".join(sorted(common))]
    gaps = []
    wanted_skills = norm_set(brief.get("skills", ""))
    talent_skills = norm_set(talent.get("skills", ""))
    if wanted_skills:
        overlap = wanted_skills & talent_skills
        ratio = len(overlap) / len(wanted_skills)
        score += 25 * ratio
        if overlap:
            reasons.append("Compétences communes : " + ", ".join(sorted(overlap)))
        missing = wanted_skills - talent_skills
        if missing:
            gaps.append("À vérifier : " + ", ".join(sorted(missing)))
    else:
        score += 12.5
    location = (brief.get("location") or "").strip().lower()
    talent_location = (talent.get("location") or "").strip().lower()
    if location and talent_location and location == talent_location:
        score += 5
        reasons.append("Zone géographique compatible")
    return {"talent": talent, "score": min(round(score, 1), 100), "reasons": reasons, "gaps": gaps}

def euro(value):
    return f"{value:,.2f} €".replace(",", " ").replace(".", ",")

def compute_price(preparation_hours, production_hours, postproduction_hours, preparation_rate, production_rate, postproduction_rate, base_rights, selections, coeffs, expenses, margin_pct, discount_pct):
    preparation = preparation_hours * preparation_rate
    production = production_hours * production_rate
    postproduction = postproduction_hours * postproduction_rate
    production_total = preparation + production + postproduction
    details = []
    rights_factor = 1.0
    for criterion, selection in selections.items():
        idx = CRITERION_OPTIONS[criterion].index(selection)
        coef = float(coeffs[criterion][idx])
        rights_factor *= coef
        details.append((criterion, selection, coef))
    rights = base_rights * rights_factor
    subtotal = production_total + rights + expenses
    margin = subtotal * margin_pct / 100
    before_discount = subtotal + margin
    discount = before_discount * discount_pct / 100
    total = max(0.0, before_discount - discount)
    return {"preparation": preparation, "production": production, "postproduction": postproduction, "base": production_total, "rights_factor": rights_factor, "rights": rights, "expenses": expenses, "margin": margin, "discount": discount, "total": total, "details": details}

def build_quote_html(client, project, talent_name, pricing, notes, validity):
    rows = "".join(
        f"<tr><td>{escape(c)}</td><td>{escape(level)}</td><td>{coef:.2f}</td></tr>"
        for c, level, coef in pricing["details"]
    )
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Devis - {escape(project)}</title>
<style>body{{font-family:Arial,sans-serif;color:#21313D;margin:40px}}h1{{color:#18354A}}.box{{background:#EAF7F5;padding:16px;border-radius:10px}}table{{border-collapse:collapse;width:100%;margin:18px 0}}th,td{{border:1px solid #DDE6EA;padding:9px;text-align:left}}th{{background:#18354A;color:white}}.total{{font-size:22px;color:#0B7E76;font-weight:700}}small{{color:#65727A}}</style></head><body>
<h1>DEVIS INDICATIF</h1><div class='box'><b>Client :</b> {escape(client)}<br><b>Projet :</b> {escape(project)}<br><b>Talent pressenti :</b> {escape(talent_name or 'À confirmer')}<br><b>Date :</b> {datetime.now().strftime('%d/%m/%Y')}<br><b>Validité :</b> {validity} jours</div>
<h2>Détail financier</h2><table><tr><th>Poste</th><th>Montant HT</th></tr><tr><td>Préparation</td><td>{euro(pricing['preparation'])}</td></tr><tr><td>Production</td><td>{euro(pricing['production'])}</td></tr><tr><td>Postproduction</td><td>{euro(pricing['postproduction'])}</td></tr><tr><td>Droits d'utilisation</td><td>{euro(pricing['rights'])}</td></tr><tr><td>Frais</td><td>{euro(pricing['expenses'])}</td></tr><tr><td>Honoraires / marge</td><td>{euro(pricing['margin'])}</td></tr><tr><td>Remise</td><td>- {euro(pricing['discount'])}</td></tr></table>
<p class='total'>Total HT : {euro(pricing['total'])}</p><h2>Paramètres de droits</h2><table><tr><th>Critère</th><th>Niveau</th><th>Coefficient</th></tr>{rows}</table>
<h2>Notes et conditions</h2><p>{escape(notes).replace(chr(10), '<br>')}</p><small>Document de travail à valider avant envoi. Les coefficients constituent une aide à la tarification et ne remplacent pas une analyse juridique ou fiscale adaptée.</small></body></html>"""

st.markdown("<div class='main-title'><h1>🎨 ESN Artistique</h1><p>Talents, briefs, matching, simulateur de droits et devis.</p></div>", unsafe_allow_html=True)

tabs = st.tabs(["Talents", "Briefs", "Matching", "Simulateur", "Devis", "Suivi", "Sauvegarde"])

with tabs[0]:
    st.header("Talents")
    with st.form("talent_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Nom du talent *")
        professions = c2.multiselect("Profession(s) *", PROFESSIONS)
        skills = c1.text_area("Compétences / styles / logiciels", placeholder="concert, portrait, Premiere Pro, beauté...")
        location = c2.text_input("Zone géographique")
        preparation_rate = c1.number_input("Tarif préparation / heure HT (€)", min_value=0.0, step=10.0)
        production_rate = c2.number_input("Tarif production / heure HT (€)", min_value=0.0, step=10.0)
        postproduction_rate = c1.number_input("Tarif postproduction / heure HT (€)", min_value=0.0, step=10.0)
        base_rights = c2.number_input("Base de droits d'utilisation HT (€)", min_value=0.0, step=50.0)
        portfolio = c2.text_input("Portfolio / lien")
        notes = st.text_area("Notes")
        if st.form_submit_button("Ajouter le talent"):
            if not name or not professions:
                st.error("Le nom et au moins une profession sont obligatoires.")
            else:
                st.session_state.talents.append({"id": datetime.now().timestamp(), "name": name, "professions": professions, "skills": skills, "location": location, "preparation_rate": preparation_rate, "production_rate": production_rate, "postproduction_rate": postproduction_rate, "base_rights": base_rights, "portfolio": portfolio, "notes": notes})
                st.success("Talent ajouté.")
    for i, t in enumerate(st.session_state.talents):
        with st.expander(f"{t['name']} - {', '.join(t.get('professions', []))}"):
            st.write(t)
            if st.button("Supprimer", key=f"del_t_{i}"):
                st.session_state.talents.pop(i); st.rerun()

with tabs[1]:
    st.header("Briefs clients")
    with st.form("brief_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        client = c1.text_input("Client *")
        title = c2.text_input("Nom du projet *")
        professions = c1.multiselect("Profession(s) recherchée(s) *", PROFESSIONS)
        skills = c2.text_area("Compétences / style recherchés")
        budget = c1.number_input("Budget ou plafond HT (€)", min_value=0.0, step=100.0)
        location = c2.text_input("Lieu / zone")
        description = st.text_area("Description du besoin")
        if st.form_submit_button("Créer le brief"):
            if not client or not title or not professions:
                st.error("Client, projet et profession sont obligatoires.")
            else:
                st.session_state.briefs.append({"id": datetime.now().timestamp(), "client": client, "title": title, "professions": professions, "skills": skills, "budget": budget, "location": location, "description": description})
                st.success("Brief créé.")
    for i, b in enumerate(st.session_state.briefs):
        with st.expander(f"{b['client']} - {b['title']}"):
            st.write(b)
            if st.button("Supprimer", key=f"del_b_{i}"):
                st.session_state.briefs.pop(i); st.rerun()

with tabs[2]:
    st.header("Matching")
    if not st.session_state.briefs:
        st.info("Crée au moins un brief.")
    else:
        brief_idx = st.selectbox("Brief", range(len(st.session_state.briefs)), format_func=lambda i: f"{st.session_state.briefs[i]['client']} - {st.session_state.briefs[i]['title']}")
        talent_count = len(st.session_state.talents)
        if talent_count == 0:
            st.warning("Ajoute au moins un talent avant de lancer le matching.")
            number_of_profiles = 0
        elif talent_count == 1:
            st.info("Un seul talent est disponible.")
            number_of_profiles = 1
        else:
            number_of_profiles = st.slider("Nombre de profils à présenter", 1, min(3, talent_count), min(3, talent_count), 1)
        if st.button("Lancer le matching", disabled=number_of_profiles == 0):
            brief = st.session_state.briefs[brief_idx]
            matches = [x for x in (calculate_match(t, brief) for t in st.session_state.talents) if x is not None]
            matches.sort(key=lambda x: x["score"], reverse=True)
            st.session_state.last_matches = matches[:number_of_profiles]
            if not matches:
                st.error("Aucun talent n'a une profession compatible avec ce brief.")
        for m in st.session_state.last_matches:
            st.markdown(f"<div class='card'><b>{escape(m['talent']['name'])}</b><div class='score'>{m['score']} %</div><p>{'<br>'.join(map(escape,m['reasons']))}</p><p class='small'>{'<br>'.join(map(escape,m['gaps']))}</p></div>", unsafe_allow_html=True)

with tabs[3]:
    st.header("Simulateur de tarification")
    st.write("Renseigne précisément les heures de préparation, de production et de postproduction, puis déplace les curseurs selon l'exploitation prévue.")
    talent_options = [""] + [t["name"] for t in st.session_state.talents]
    talent_name = st.selectbox("Talent utilisé pour le calcul", talent_options)
    talent = next((t for t in st.session_state.talents if t["name"] == talent_name), {})
    st.subheader("Temps de travail")
    c1, c2, c3 = st.columns(3)
    preparation_hours = c1.number_input("Heures de préparation", min_value=0.0, value=2.0, step=0.5)
    production_hours = c2.number_input("Heures de production", min_value=0.0, value=8.0, step=0.5)
    postproduction_hours = c3.number_input("Heures de postproduction", min_value=0.0, value=3.0, step=0.5)
    c1, c2, c3 = st.columns(3)
    preparation_rate = c1.number_input("Tarif préparation / heure HT (€)", min_value=0.0, value=float(talent.get("preparation_rate",0) or 0), step=10.0)
    production_rate = c2.number_input("Tarif production / heure HT (€)", min_value=0.0, value=float(talent.get("production_rate",0) or 0), step=10.0)
    postproduction_rate = c3.number_input("Tarif postproduction / heure HT (€)", min_value=0.0, value=float(talent.get("postproduction_rate",0) or 0), step=10.0)
    st.subheader("Droits d'utilisation")
    base_rights = st.number_input("Base de droits HT (€)", min_value=0.0, value=float(talent.get("base_rights",0) or 0), step=50.0)
    selections = {}
    for criterion, options in CRITERION_OPTIONS.items():
        selection = st.select_slider(criterion, options=options, value=options[len(options)//2], key=f"slider_{criterion}")
        selections[criterion] = selection
        idx = options.index(selection)
        st.caption(f"Choix retenu : {selection} · coefficient {st.session_state.coefficients[criterion][idx]:.2f}")
    st.subheader("Frais et ajustements")
    c1, c2, c3 = st.columns(3)
    expenses = c1.number_input("Frais techniques et déplacements HT (€)", min_value=0.0, value=0.0, step=25.0)
    margin_pct = c2.number_input("Honoraires / marge (%)", min_value=0.0, max_value=100.0, value=10.0, step=1.0)
    discount_pct = c3.number_input("Remise commerciale (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
    pricing = compute_price(preparation_hours, production_hours, postproduction_hours, preparation_rate, production_rate, postproduction_rate, base_rights, selections, st.session_state.coefficients, expenses, margin_pct, discount_pct)
    st.session_state.last_pricing = pricing
    a,b,c,d = st.columns(4)
    a.metric("Temps de travail", euro(pricing["base"]))
    b.metric("Droits", euro(pricing["rights"]))
    c.metric("Coefficient cumulé", f"× {pricing['rights_factor']:.2f}")
    d.metric("Total HT", euro(pricing["total"]))
    st.dataframe([{"Critère": x, "Choix": y, "Coefficient": z} for x,y,z in pricing["details"]], use_container_width=True, hide_index=True)

with tabs[4]:
    st.header("Générer un devis")
    if not st.session_state.last_pricing:
        st.info("Calcule d'abord un tarif dans le simulateur.")
    else:
        client_default = st.session_state.briefs[-1]["client"] if st.session_state.briefs else ""
        project_default = st.session_state.briefs[-1]["title"] if st.session_state.briefs else ""
        client = st.text_input("Client", value=client_default, key="quote_client")
        project = st.text_input("Projet", value=project_default, key="quote_project")
        talent_options = [""] + [t["name"] for t in st.session_state.talents]
        talent_name = st.selectbox("Talent pressenti", talent_options)
        validity = st.number_input("Validité du devis (jours)", min_value=1, value=30)
        notes = st.text_area("Notes / conditions", value="Acompte à définir. Planning et livrables à confirmer avant démarrage.")
        html = build_quote_html(client, project, talent_name, st.session_state.last_pricing, notes, validity)
        st.download_button("Télécharger le devis HTML", html.encode("utf-8"), file_name=f"devis_{re.sub(r'[^a-zA-Z0-9]+','_',project or 'projet')}.html", mime="text/html")
        st.caption("Le fichier HTML peut être ouvert dans un navigateur puis imprimé en PDF.")

with tabs[5]:
    st.header("Suivi des opportunités")
    with st.form("opp_form", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        opp_client = c1.text_input("Client")
        opp_project = c2.text_input("Projet")
        opp_status = c3.selectbox("Statut", ["À qualifier", "Devis à préparer", "Devis envoyé", "Relance", "Gagné", "Perdu"])
        opp_amount = c1.number_input("Montant HT (€)", min_value=0.0, step=100.0)
        opp_next = c2.text_input("Prochaine action")
        opp_notes = c3.text_input("Notes")
        if st.form_submit_button("Ajouter au suivi"):
            st.session_state.opportunities.append({"client":opp_client,"project":opp_project,"status":opp_status,"amount":opp_amount,"next_action":opp_next,"notes":opp_notes})
            st.success("Opportunité ajoutée.")
    st.dataframe(st.session_state.opportunities, use_container_width=True, hide_index=True)

with tabs[6]:
    st.header("Sauvegarde et restauration")
    export_data = {"version": 3, "exported_at": datetime.now().isoformat(), "talents": st.session_state.talents, "briefs": st.session_state.briefs, "opportunities": st.session_state.opportunities, "coefficients": st.session_state.coefficients}
    st.download_button("Télécharger la sauvegarde JSON", json.dumps(export_data, ensure_ascii=False, indent=2), "esn_artistique_sauvegarde.json", "application/json")
    uploaded = st.file_uploader("Restaurer une sauvegarde JSON", type=["json"])
    if uploaded and st.button("Restaurer les données"):
        try:
            data = json.loads(uploaded.getvalue().decode("utf-8"))
            for key in ["talents", "briefs", "opportunities"]:
                st.session_state[key] = data.get(key, [])
            coeffs = data.get("coefficients")
            if isinstance(coeffs, dict) and all(k in coeffs for k in DEFAULT_COEFFICIENTS):
                st.session_state.coefficients = coeffs
            st.success("Données restaurées.")
            st.rerun()
        except Exception as exc:
            st.error(f"Sauvegarde invalide : {exc}")
