import json
import re
from datetime import date, datetime
from html import escape

import streamlit as st

st.set_page_config(page_title="Manager Créatifs", page_icon="🎨", layout="wide")

st.markdown(
    """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 4rem;}
.hero {padding: 24px; border-radius: 18px; color: white; background: linear-gradient(135deg,#18354D,#286E78); margin-bottom: 18px;}
.card {padding: 16px; border: 1px solid #DDE6EA; border-radius: 14px; background: white; margin: 10px 0;}
.card-green {padding: 16px; border-left: 5px solid #18A99A; border-radius: 10px; background: #EAF7F5; margin: 10px 0;}
.card-orange {padding: 16px; border-left: 5px solid #E8A23A; border-radius: 10px; background: #FFF4E5; margin: 10px 0;}
.card-red {padding: 16px; border-left: 5px solid #C84A4A; border-radius: 10px; background: #FDEEEE; margin: 10px 0;}
.small {color: #65727A; font-size: 0.9rem;}
div[data-testid="stMetric"] {border: 1px solid #DDE6EA; padding: 14px; border-radius: 12px; background: white;}
.stButton > button {background:#18A99A; color:white; border:none; font-weight:700;}
</style>
""",
    unsafe_allow_html=True,
)

PROFESSIONS = [
    "Photographe", "Vidéaste", "Monteur vidéo", "Pilote de drone",
    "Graphiste", "Motion designer", "Directeur artistique",
    "Community manager", "Maquilleur / Maquilleuse", "Styliste",
    "Illustrateur / Illustratrice", "Retoucheur / Retoucheuse",
    "Sound designer", "Ingénieur du son", "Rédacteur / Rédactrice",
]

IMPORTANCE_OPTIONS = ["Faible", "Mineur", "Moyen", "Important", "Très important"]
URGENCY_OPTIONS = ["Faible", "Mineure", "Moyenne", "Importante", "Très importante"]
CRITERION_OPTIONS = {
    "Support / usage": ["Usage interne", "Site / communication organique", "Communication commerciale", "Édition / campagne", "Publicité majeure"],
    "Diffusion": ["Moins de 1 000", "1 000 à 10 000", "10 000 à 100 000", "100 000 à 1 million", "Plus de 1 million"],
    "Territoire": ["Local", "Régional", "France", "Europe", "Monde"],
    "Durée": ["Ponctuelle", "Moins de 6 mois", "Jusqu'à 1 an", "Jusqu'à 3 ans", "Plus de 3 ans"],
    "Exclusivité": ["Aucune", "Limitée", "Sectorielle", "Étendue", "Totale"],
}

DEFAULT_COEFFICIENTS = {
    "Support / usage": [0.25, 0.50, 1.00, 1.75, 2.75],
    "Diffusion": [0.20, 0.50, 1.00, 2.25, 4.00],
    "Territoire": [0.20, 0.55, 1.00, 1.70, 2.60],
    "Durée": [0.20, 0.55, 1.00, 1.75, 2.75],
    "Exclusivité": [0.00, 0.50, 1.00, 2.25, 4.00],
}

BUDGET_MODES = ["Enveloppe précise", "Fourchette", "Budget non communiqué"]


def init_state():
    defaults = {
        "briefs": [],
        "opportunities": [],
        "coefficients": {k: list(v) for k, v in DEFAULT_COEFFICIENTS.items()},
        "selected_brief_index": 0,
        "last_pricing": None,
        "last_context": None,
        "last_analysis": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


def euro(value):
    return f"{float(value):,.2f} €".replace(",", " ").replace(".", ",")


def fmt_date(value):
    if not value:
        return "Non renseignée"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y")
    except ValueError:
        return str(value)


def clean_text(value):
    return str(value or "").strip()


def estimate_diffusion(followers, views, paid_media):
    audience = max(int(followers or 0), int(views or 0))
    if paid_media >= 10000 or audience > 1_000_000:
        return "Plus de 1 million"
    if paid_media >= 3000 or audience > 100_000:
        return "100 000 à 1 million"
    if paid_media > 0 or audience > 10_000:
        return "10 000 à 100 000"
    if audience > 1_000:
        return "1 000 à 10 000"
    if audience > 0:
        return "Moins de 1 000"
    return None


def date_urgency(event_date, delivery_date, brief_date):
    start = datetime.fromisoformat(brief_date).date() if isinstance(brief_date, str) else brief_date
    event = datetime.fromisoformat(event_date).date() if isinstance(event_date, str) else event_date
    delivery = datetime.fromisoformat(delivery_date).date() if isinstance(delivery_date, str) else delivery_date
    nearest = min(event, delivery)
    days = (nearest - start).days
    if days <= 3:
        return "Très importante", days
    if days <= 7:
        return "Importante", days
    if days <= 21:
        return "Moyenne", days
    if days <= 45:
        return "Mineure", days
    return "Faible", days


def infer_importance(brief):
    score = 0
    if brief.get("paid_media_budget", 0) > 0:
        score += 2
    if brief.get("expected_views", 0) >= 100_000:
        score += 2
    if brief.get("profile_count", 1) >= 3:
        score += 1
    if brief.get("project_type") in ["Campagne", "Événement"]:
        score += 1
    if brief.get("territory_criterion") in ["Europe", "Monde"]:
        score += 1
    if brief.get("exclusivity_criterion") in ["Étendue", "Totale"]:
        score += 2
    if score >= 6:
        return "Très important"
    if score >= 4:
        return "Important"
    if score >= 2:
        return "Moyen"
    if score == 1:
        return "Mineur"
    return "Faible"


def analyze_brief(brief):
    """Analyse hybride déterministe : règles métier + synthèse automatique, sans API externe."""
    required_checks = {
        "Client": brief.get("client"),
        "Projet": brief.get("title"),
        "Métiers": brief.get("professions"),
        "Objectif": brief.get("business_goal"),
        "Livrables": brief.get("deliverables"),
        "Lieu / modalité": brief.get("location") or brief.get("work_mode"),
        "Budget": brief.get("budget_mode") != "Budget non communiqué",
        "Support / usage": brief.get("support_criterion"),
        "Diffusion": brief.get("diffusion_criterion") or brief.get("expected_views") or brief.get("social_followers"),
        "Territoire": brief.get("territory_criterion"),
        "Durée": brief.get("duration_criterion"),
        "Exclusivité": brief.get("exclusivity_criterion"),
        "Validation": brief.get("approval"),
    }
    completed = sum(bool(v) for v in required_checks.values())
    completeness = round(completed / len(required_checks) * 100)
    missing = [name for name, value in required_checks.items() if not value]

    warnings = []
    recommendations = []
    questions = []

    event = datetime.fromisoformat(brief["event_date"]).date()
    delivery = datetime.fromisoformat(brief["delivery_date"]).date()
    entry = datetime.fromisoformat(brief["brief_date"]).date()
    urgency, days = date_urgency(event, delivery, entry)

    if delivery < event:
        warnings.append("La date de rendu est antérieure à la date de l'événement.")
    if days < 0:
        warnings.append("Au moins une échéance est déjà dépassée.")
    elif days <= 7:
        warnings.append(f"Échéance très courte : {days} jour(s) avant la première date critique.")
    elif days <= 21:
        recommendations.append(f"Prévoir une validation rapide : {days} jour(s) avant la première échéance.")

    if not clean_text(brief.get("deliverables")):
        questions.append("Quels sont les livrables exacts, leurs formats et leurs quantités ?")
    if not clean_text(brief.get("business_goal")):
        questions.append("Quel résultat business ou de communication le client attend-il ?")
    if brief.get("revisions") in [None, "", "À confirmer"]:
        questions.append("Combien d'allers-retours et de corrections doivent être inclus ?")
    if not brief.get("support_criterion"):
        questions.append("Sur quels supports les contenus seront-ils exploités ?")
    if not brief.get("territory_criterion"):
        questions.append("Sur quel territoire les contenus seront-ils diffusés ?")
    if not brief.get("duration_criterion"):
        questions.append("Pendant combien de temps les droits d'utilisation sont-ils demandés ?")
    if not brief.get("exclusivity_criterion"):
        questions.append("Une exclusivité est-elle demandée, et sur quel périmètre ?")
    if brief.get("budget_mode") == "Budget non communiqué":
        warnings.append("Aucune enveloppe budgétaire n'est communiquée.")
        questions.append("Quelle enveloppe le client a-t-il prévue, droits et frais inclus ?")
    if brief.get("paid_media_budget", 0) > 0 and not brief.get("diffusion_criterion"):
        warnings.append("Un achat média est prévu mais le niveau de diffusion n'est pas confirmé.")
    if brief.get("exclusivity_criterion") in ["Étendue", "Totale"]:
        warnings.append("L'exclusivité demandée augmente fortement la valeur des droits.")
    if brief.get("territory_criterion") == "Monde":
        warnings.append("Une exploitation mondiale est demandée : vérifier si ce périmètre est réellement nécessaire.")
    if brief.get("duration_criterion") == "Plus de 3 ans":
        warnings.append("La durée excède trois ans : envisager une durée limitée ou renouvelable.")

    diffusion = brief.get("diffusion_criterion") or estimate_diffusion(
        brief.get("social_followers", 0),
        brief.get("expected_views", 0),
        brief.get("paid_media_budget", 0),
    ) or "10 000 à 100 000"

    selections = {
        "Support / usage": brief.get("support_criterion") or "Communication commerciale",
        "Diffusion": diffusion,
        "Territoire": brief.get("territory_criterion") or "France",
        "Durée": brief.get("duration_criterion") or "Jusqu'à 1 an",
        "Exclusivité": brief.get("exclusivity_criterion") or "Aucune",
    }
    importance = brief.get("importance_criterion") or infer_importance(brief)
    supplied_urgency = brief.get("urgency_criterion")
    final_urgency = supplied_urgency or urgency

    if not warnings:
        recommendations.append("Aucune incohérence majeure détectée dans les informations saisies.")
    recommendations.append("Faire valider le périmètre, les livrables, les droits et le nombre de corrections avant devis définitif.")

    summary = (
        f"{brief.get('client', 'Client à préciser')} souhaite lancer le projet "
        f"« {brief.get('title', 'Projet à préciser')} » de type {brief.get('project_type', 'à préciser')}. "
        f"Le besoin mobilise {brief.get('profile_count', 1)} profil(s) sur les métiers : "
        f"{', '.join(brief.get('professions', [])) or 'à définir'}. "
        f"L'événement est prévu le {fmt_date(brief.get('event_date'))} et le rendu le {fmt_date(brief.get('delivery_date'))}. "
        f"Les livrables identifiés sont : {brief.get('deliverables') or 'à confirmer'}."
    )

    return {
        "generated_at": datetime.now().isoformat(),
        "completeness": completeness,
        "missing": missing,
        "summary": summary,
        "warnings": warnings,
        "recommendations": recommendations,
        "questions": questions,
        "suggested_importance": importance,
        "suggested_urgency": final_urgency,
        "suggested_selections": selections,
        "days_to_first_deadline": days,
    }


def compute_price(prep_h, production_h, post_h, prep_rate, production_rate, post_rate,
                  importance, urgency, selections, expenses, margin_pct, discount_pct):
    creative_cost = prep_h * prep_rate + production_h * production_rate + post_h * post_rate
    importance_factor = {
        "Faible": 0.10, "Mineur": 0.20, "Moyen": 0.35,
        "Important": 0.55, "Très important": 0.80,
    }[importance]
    base_rights = creative_cost * importance_factor
    details = []
    coefficient_total = 0.0
    for criterion, selection in selections.items():
        idx = CRITERION_OPTIONS[criterion].index(selection)
        coefficient = float(st.session_state.coefficients[criterion][idx])
        details.append({"Critère": criterion, "Niveau": selection, "Coefficient": coefficient})
        coefficient_total += coefficient
    rights = base_rights * coefficient_total
    urgency_factor = {
        "Faible": 0.00, "Mineure": 0.05, "Moyenne": 0.10,
        "Importante": 0.20, "Très importante": 0.35,
    }[urgency]
    urgency_amount = creative_cost * urgency_factor
    subtotal_before_margin = creative_cost + rights + urgency_amount + expenses
    margin_amount = subtotal_before_margin * margin_pct / 100
    before_discount = subtotal_before_margin + margin_amount
    discount_amount = before_discount * discount_pct / 100
    total = max(0.0, before_discount - discount_amount)
    return {
        "creative_cost": creative_cost,
        "base_rights": base_rights,
        "rights": rights,
        "urgency_amount": urgency_amount,
        "expenses": expenses,
        "subtotal_before_margin": subtotal_before_margin,
        "margin_pct": margin_pct,
        "margin_amount": margin_amount,
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "coefficient_total": coefficient_total,
        "details": details,
        "total": total,
    }


def analysis_markdown(brief, analysis):
    warnings = "\n".join(f"- {x}" for x in analysis["warnings"]) or "- Aucun point bloquant détecté."
    questions = "\n".join(f"- {x}" for x in analysis["questions"]) or "- Aucune question prioritaire supplémentaire."
    recommendations = "\n".join(f"- {x}" for x in analysis["recommendations"])
    missing = ", ".join(analysis["missing"]) or "Aucune"
    parameters = "\n".join(f"- **{k}** : {v}" for k, v in analysis["suggested_selections"].items())
    return f"""# Analyse automatique du brief

## Synthèse
{analysis['summary']}

## Complétude
- Niveau de complétude : **{analysis['completeness']} %**
- Informations manquantes : {missing}

## Points de vigilance
{warnings}

## Questions à poser au client
{questions}

## Recommandations
{recommendations}

## Paramètres proposés pour le simulateur
- **Importance** : {analysis['suggested_importance']}
- **Urgence** : {analysis['suggested_urgency']}
{parameters}

> Analyse automatique fondée sur des règles métier. Elle facilite le cadrage mais ne constitue pas un avis juridique, fiscal ou comptable.
"""


def build_quote_html(brief, pricing, context):
    details = "".join(
        f"<tr><td>{escape(str(row['Critère']))}</td><td>{escape(str(row['Niveau']))}</td><td>{row['Coefficient']:.2f}</td></tr>"
        for row in pricing["details"]
    )
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Devis - {escape(brief.get('title','Projet'))}</title>
<style>body{{font-family:Arial,sans-serif;color:#21313D;margin:40px}}h1{{color:#18354A}}.box{{background:#EAF7F5;padding:16px;border-radius:10px}}table{{border-collapse:collapse;width:100%;margin:18px 0}}th,td{{border:1px solid #DDE6EA;padding:9px;text-align:left}}th{{background:#18354A;color:white}}.total{{font-size:22px;color:#0B7E76;font-weight:700}}small{{color:#65727A}}</style></head><body>
<h1>DEVIS INDICATIF</h1><div class='box'><b>Client :</b> {escape(brief.get('client',''))}<br><b>Projet :</b> {escape(brief.get('title',''))}<br><b>Événement :</b> {fmt_date(brief.get('event_date'))}<br><b>Rendu :</b> {fmt_date(brief.get('delivery_date'))}<br><b>Date du devis :</b> {datetime.now().strftime('%d/%m/%Y')}</div>
<h2>Détail financier</h2><table><tr><th>Poste</th><th>Montant HT</th></tr><tr><td>Production créative</td><td>{euro(pricing['creative_cost'])}</td></tr><tr><td>Droits d'utilisation</td><td>{euro(pricing['rights'])}</td></tr><tr><td>Urgence</td><td>{euro(pricing['urgency_amount'])}</td></tr><tr><td>Frais</td><td>{euro(pricing['expenses'])}</td></tr><tr><td>Marge / honoraires</td><td>{euro(pricing['margin_amount'])}</td></tr><tr><td>Remise</td><td>- {euro(pricing['discount_amount'])}</td></tr></table>
<p class='total'>Total HT : {euro(pricing['total'])}</p><h2>Paramètres de droits</h2><table><tr><th>Critère</th><th>Niveau</th><th>Coefficient</th></tr>{details}</table>
<p><b>Importance :</b> {escape(context['importance'])}<br><b>Urgence :</b> {escape(context['urgency'])}</p><small>Document de travail à valider avant envoi.</small></body></html>"""


st.markdown("<div class='hero'><h1>🎨 Manager Créatifs</h1><p>Brief, analyse hybride automatique, simulateur, devis et suivi commercial.</p></div>", unsafe_allow_html=True)

tabs = st.tabs(["Briefs", "Simulateur", "Devis", "Suivi", "Analyse contractuelle", "Sauvegarde"])

with tabs[0]:
    st.header("Brief de mission")
    st.caption("L'analyse hybride est générée automatiquement à l'enregistrement du brief, sans clé API.")

    with st.form("brief_form", clear_on_submit=True):
        st.subheader("1. Repères et dates")
        c1, c2, c3 = st.columns(3)
        brief_date = c1.date_input("Date du jour / date de saisie", value=date.today(), format="DD/MM/YYYY")
        event_date = c2.date_input("Date de l'événement", value=date.today(), format="DD/MM/YYYY")
        delivery_date = c3.date_input("Date de rendu", value=date.today(), format="DD/MM/YYYY")

        c1, c2, c3 = st.columns(3)
        client = c1.text_input("Client *")
        contact = c2.text_input("Contact principal")
        role = c3.text_input("Fonction du contact")
        title = c1.text_input("Projet *")
        project_type = c2.selectbox("Type", ["À préciser", "Photo", "Vidéo", "Graphisme", "Motion design", "Contenu social", "Événement", "Campagne", "Autre"])
        profiles = c3.number_input("Nombre de profils", min_value=1, value=1, step=1)
        jobs = st.multiselect("Métiers nécessaires *", PROFESSIONS)
        multi = st.radio("Un profil peut-il cumuler plusieurs métiers ?", ["Oui", "Non", "À confirmer"], horizontal=True)

        st.subheader("2. Besoin")
        c1, c2 = st.columns(2)
        location = c1.text_input("Lieu / zone")
        work_mode = c2.selectbox("Modalité", ["Sur site", "À distance", "Hybride", "À confirmer"])
        goal = c1.text_area("Objectif business / communication")
        target = c2.text_area("Public cible")
        message = c1.text_area("Message / action attendue")
        deliverables = c2.text_area("Livrables")
        skills = c1.text_area("Style, compétences, logiciels")
        references = c2.text_area("Références / contre-exemples")

        st.subheader("3. Critères directs du simulateur")
        c1, c2, c3 = st.columns(3)
        prep_hours = c1.number_input("Heures de préparation estimées", min_value=0.0, step=0.5)
        production_hours = c2.number_input("Heures de production estimées", min_value=0.0, step=0.5)
        post_hours = c3.number_input("Heures de postproduction estimées", min_value=0.0, step=0.5)

        c1, c2, c3 = st.columns(3)
        importance = c1.selectbox("Importance du projet", ["À confirmer"] + IMPORTANCE_OPTIONS)
        urgency = c2.selectbox("Urgence", ["À confirmer"] + URGENCY_OPTIONS)
        support = c3.selectbox("Support / usage", ["À confirmer"] + CRITERION_OPTIONS["Support / usage"])
        diffusion = c1.selectbox("Diffusion estimée", ["À estimer depuis l'audience"] + CRITERION_OPTIONS["Diffusion"])
        territory = c2.selectbox("Territoire", ["À confirmer"] + CRITERION_OPTIONS["Territoire"])
        duration = c3.selectbox("Durée d'exploitation", ["À confirmer"] + CRITERION_OPTIONS["Durée"])
        exclusivity = c1.selectbox("Exclusivité", ["À confirmer"] + CRITERION_OPTIONS["Exclusivité"])
        followers = c2.number_input("Nombre d'abonnés sur les réseaux", min_value=0, step=100)
        views = c3.number_input("Nombre de vues / portée attendue", min_value=0, step=1000)
        paid_media = c1.number_input("Budget d'achat média HT", min_value=0.0, step=100.0)
        estimated_expenses = c2.number_input("Frais déjà estimés HT", min_value=0.0, step=25.0)
        revisions = c3.selectbox("Allers-retours envisagés", ["À confirmer", "1", "2", "3", "Plus de 3"])

        st.subheader("4. Budget, validation et risques")
        budget_mode = st.selectbox("Situation budgétaire", BUDGET_MODES)
        c1, c2 = st.columns(2)
        exact = minimum = maximum = 0.0
        if budget_mode == "Enveloppe précise":
            exact = c1.number_input("Enveloppe précise HT", min_value=0.0, step=100.0)
        elif budget_mode == "Fourchette":
            minimum = c1.number_input("Minimum HT", min_value=0.0, step=100.0)
            maximum = c2.number_input("Maximum HT", min_value=0.0, step=100.0)
        budget_includes = st.multiselect("Éléments inclus dans le budget", ["Préparation", "Production", "Postproduction", "Talents", "Matériel", "Déplacements", "Droits", "Marge", "Taxes", "Achat média", "À confirmer"])
        approval = c1.text_area("Décideur final et validation")
        constraints = c2.text_area("Contraintes techniques, légales, sécurité, RSE")
        inputs = c1.text_area("Éléments fournis par le client")
        usage_notes = c2.text_area("Précisions sur les droits et utilisations")
        description = st.text_area("Informations complémentaires")

        submitted = st.form_submit_button("Enregistrer et analyser automatiquement le brief")
        if submitted:
            if not client or not title or not jobs:
                st.error("Client, projet et au moins un métier sont obligatoires.")
            else:
                brief = {
                    "id": datetime.now().timestamp(),
                    "brief_date": brief_date.isoformat(),
                    "event_date": event_date.isoformat(),
                    "delivery_date": delivery_date.isoformat(),
                    "client": client,
                    "contact_name": contact,
                    "contact_role": role,
                    "title": title,
                    "project_type": project_type,
                    "profile_count": int(profiles),
                    "professions": jobs,
                    "multi_role_allowed": multi,
                    "location": location,
                    "work_mode": work_mode,
                    "business_goal": goal,
                    "target_audience": target,
                    "key_message": message,
                    "deliverables": deliverables,
                    "skills": skills,
                    "references": references,
                    "prep_hours_estimate": prep_hours,
                    "production_hours_estimate": production_hours,
                    "post_hours_estimate": post_hours,
                    "importance_criterion": None if importance == "À confirmer" else importance,
                    "urgency_criterion": None if urgency == "À confirmer" else urgency,
                    "support_criterion": None if support == "À confirmer" else support,
                    "diffusion_criterion": None if diffusion == "À estimer depuis l'audience" else diffusion,
                    "social_followers": int(followers),
                    "expected_views": int(views),
                    "paid_media_budget": paid_media,
                    "territory_criterion": None if territory == "À confirmer" else territory,
                    "duration_criterion": None if duration == "À confirmer" else duration,
                    "exclusivity_criterion": None if exclusivity == "À confirmer" else exclusivity,
                    "estimated_expenses": estimated_expenses,
                    "revisions": revisions,
                    "budget_mode": budget_mode,
                    "budget_exact": exact,
                    "budget_min": minimum,
                    "budget_max": maximum,
                    "budget_includes": budget_includes,
                    "approval": approval,
                    "constraints": constraints,
                    "client_inputs": inputs,
                    "usage_notes": usage_notes,
                    "description": description,
                }
                analysis = analyze_brief(brief)
                brief["hybrid_analysis"] = analysis
                st.session_state.briefs.append(brief)
                st.session_state.selected_brief_index = len(st.session_state.briefs) - 1
                st.session_state.last_analysis = analysis
                st.success("Brief enregistré et analysé automatiquement.")

    if st.session_state.briefs:
        st.divider()
        st.subheader("Briefs enregistrés et analyses automatiques")
        selected = st.selectbox(
            "Sélectionner un brief",
            range(len(st.session_state.briefs)),
            index=min(st.session_state.selected_brief_index, len(st.session_state.briefs) - 1),
            format_func=lambda i: f"{st.session_state.briefs[i]['client']} - {st.session_state.briefs[i]['title']}",
            key="brief_display_select",
        )
        st.session_state.selected_brief_index = selected
        brief = st.session_state.briefs[selected]
        analysis = brief.get("hybrid_analysis") or analyze_brief(brief)
        brief["hybrid_analysis"] = analysis

        c1, c2, c3 = st.columns(3)
        c1.metric("Complétude", f"{analysis['completeness']} %")
        c2.metric("Points de vigilance", len(analysis["warnings"]))
        c3.metric("Questions à poser", len(analysis["questions"]))

        st.markdown(f"<div class='card-green'><b>Synthèse automatique</b><br>{escape(analysis['summary'])}</div>", unsafe_allow_html=True)

        left, right = st.columns(2)
        with left:
            st.subheader("Points de vigilance")
            if analysis["warnings"]:
                for item in analysis["warnings"]:
                    st.warning(item)
            else:
                st.success("Aucun point bloquant détecté.")
            st.subheader("Questions à poser")
            for item in analysis["questions"]:
                st.write(f"- {item}")
        with right:
            st.subheader("Paramètres proposés")
            st.write(f"**Importance :** {analysis['suggested_importance']}")
            st.write(f"**Urgence :** {analysis['suggested_urgency']}")
            for criterion, value in analysis["suggested_selections"].items():
                st.write(f"**{criterion} :** {value}")
            st.subheader("Recommandations")
            for item in analysis["recommendations"]:
                st.write(f"- {item}")

        report = analysis_markdown(brief, analysis)
        st.download_button(
            "Télécharger l'analyse du brief",
            report.encode("utf-8"),
            file_name=f"analyse_{re.sub(r'[^a-zA-Z0-9]+', '_', brief['title'])}.md",
            mime="text/markdown",
        )
        c1, c2 = st.columns(2)
        if c1.button("Recalculer l'analyse", key="reanalyze"):
            analysis = analyze_brief(brief)
            brief["hybrid_analysis"] = analysis
            st.session_state.last_analysis = analysis
            st.rerun()
        if c2.button("Supprimer ce brief", key="delete_brief"):
            st.session_state.briefs.pop(selected)
            st.session_state.selected_brief_index = 0
            st.rerun()

with tabs[1]:
    st.header("Simulateur")
    if not st.session_state.briefs:
        st.info("Crée d'abord un brief. Son analyse automatique alimentera le simulateur.")
    else:
        brief_idx = st.selectbox(
            "Brief à simuler",
            range(len(st.session_state.briefs)),
            index=min(st.session_state.selected_brief_index, len(st.session_state.briefs) - 1),
            format_func=lambda i: f"{st.session_state.briefs[i]['client']} - {st.session_state.briefs[i]['title']}",
            key="sim_brief",
        )
        brief = st.session_state.briefs[brief_idx]
        analysis = brief.get("hybrid_analysis") or analyze_brief(brief)

        st.markdown("<div class='card-green'><b>Préremplissage automatique</b><br>Les niveaux proposés proviennent de l'analyse hybride du brief. Chaque valeur reste modifiable pour le projet.</div>", unsafe_allow_html=True)

        with st.expander("Modifier les coefficients du projet"):
            edited = {}
            for criterion, current in st.session_state.coefficients.items():
                st.write(f"**{criterion}**")
                cols = st.columns(5)
                edited[criterion] = [
                    cols[i].number_input(
                        IMPORTANCE_OPTIONS[i], min_value=0.0, max_value=10.0,
                        value=float(current[i]), step=0.05, key=f"coef_{criterion}_{i}"
                    ) for i in range(5)
                ]
            c1, c2 = st.columns(2)
            if c1.button("Appliquer les coefficients"):
                st.session_state.coefficients = edited
                st.success("Coefficients appliqués.")
            if c2.button("Restaurer les coefficients recommandés"):
                st.session_state.coefficients = {k: list(v) for k, v in DEFAULT_COEFFICIENTS.items()}
                st.rerun()

        defaults = analysis["suggested_selections"]
        c1, c2, c3 = st.columns(3)
        prep_h = c1.number_input("Heures de préparation", min_value=0.0, value=float(brief.get("prep_hours_estimate", 0)), step=0.5)
        production_h = c2.number_input("Heures de production", min_value=0.0, value=float(brief.get("production_hours_estimate", 0)), step=0.5)
        post_h = c3.number_input("Heures de postproduction", min_value=0.0, value=float(brief.get("post_hours_estimate", 0)), step=0.5)
        c1, c2, c3 = st.columns(3)
        prep_rate = c1.number_input("Tarif préparation / h", min_value=0.0, value=50.0, step=5.0)
        production_rate = c2.number_input("Tarif production / h", min_value=0.0, value=80.0, step=5.0)
        post_rate = c3.number_input("Tarif postproduction / h", min_value=0.0, value=60.0, step=5.0)

        importance = st.select_slider(
            "Importance", options=IMPORTANCE_OPTIONS,
            value=analysis["suggested_importance"], key=f"importance_{brief['id']}"
        )
        urgency = st.select_slider(
            "Urgence", options=URGENCY_OPTIONS,
            value=analysis["suggested_urgency"], key=f"urgency_{brief['id']}"
        )
        selections = {}
        for criterion, options in CRITERION_OPTIONS.items():
            selections[criterion] = st.select_slider(
                criterion, options=options, value=defaults[criterion],
                key=f"criterion_{criterion}_{brief['id']}"
            )

        c1, c2, c3 = st.columns(3)
        expenses = c1.number_input("Frais HT", min_value=0.0, value=float(brief.get("estimated_expenses", 0)), step=25.0)
        margin_pct = c2.number_input("Marge / honoraires (%)", min_value=0.0, max_value=100.0, value=10.0)
        discount_pct = c3.number_input("Remise (%)", min_value=0.0, max_value=100.0, value=0.0)

        pricing = compute_price(
            prep_h, production_h, post_h, prep_rate, production_rate, post_rate,
            importance, urgency, selections, expenses, margin_pct, discount_pct,
        )
        st.session_state.last_pricing = pricing
        st.session_state.last_context = {
            "pricing": pricing, "brief_index": brief_idx, "importance": importance,
            "urgency": urgency, "selections": selections,
        }

        cols = st.columns(6)
        metrics = [
            ("Créatif", pricing["creative_cost"]), ("Base droits", pricing["base_rights"]),
            ("Urgence", pricing["urgency_amount"]), ("Droits", pricing["rights"]),
            ("Marge", pricing["margin_amount"]), ("Total HT", pricing["total"]),
        ]
        for col, (label, value) in zip(cols, metrics):
            col.metric(label, euro(value))
        st.dataframe(pricing["details"], use_container_width=True, hide_index=True)

with tabs[2]:
    st.header("Devis")
    if not st.session_state.last_pricing or not st.session_state.last_context:
        st.info("Calcule d'abord un tarif dans le simulateur.")
    else:
        context = st.session_state.last_context
        brief = st.session_state.briefs[context["brief_index"]]
        pricing = st.session_state.last_pricing
        st.write(f"**Client :** {brief['client']}  ")
        st.write(f"**Projet :** {brief['title']}  ")
        st.write(f"**Événement :** {fmt_date(brief['event_date'])}  ")
        st.write(f"**Rendu :** {fmt_date(brief['delivery_date'])}")
        html = build_quote_html(brief, pricing, context)
        st.download_button(
            "Télécharger le devis HTML",
            html.encode("utf-8"),
            file_name=f"devis_{re.sub(r'[^a-zA-Z0-9]+', '_', brief['title'])}.html",
            mime="text/html",
        )
        st.caption("Ouvre le fichier dans un navigateur puis utilise Imprimer > Enregistrer au format PDF.")

with tabs[3]:
    st.header("Suivi commercial")
    with st.form("opp_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        opp_client = c1.text_input("Client")
        opp_project = c2.text_input("Projet")
        opp_status = c3.selectbox("Statut", ["À qualifier", "Brief reçu", "Devis à préparer", "Devis envoyé", "Relance", "Gagné", "Perdu"])
        opp_amount = c1.number_input("Montant HT", min_value=0.0, step=100.0)
        opp_next = c2.text_input("Prochaine action")
        opp_notes = c3.text_input("Notes")
        if st.form_submit_button("Ajouter au suivi"):
            st.session_state.opportunities.append({
                "client": opp_client, "project": opp_project, "status": opp_status,
                "amount": opp_amount, "next_action": opp_next, "notes": opp_notes,
            })
            st.success("Opportunité ajoutée.")
    st.dataframe(st.session_state.opportunities, use_container_width=True, hide_index=True)

with tabs[4]:
    st.header("Analyse contractuelle assistée")
    st.warning("Cette fonctionnalité sert au repérage opérationnel. Elle ne remplace pas un avis juridique professionnel.")
    contract_text = st.text_area("Colle ici une clause ou un contrat", height=220)
    if st.button("Analyser les points de vigilance"):
        text = contract_text.lower()
        checks = [
            ("acompte", "Vérifier le montant de l'acompte et son exigibilité avant démarrage."),
            ("annulation", "Vérifier les frais d'annulation et les délais de prévenance."),
            ("exclusiv", "Délimiter précisément l'exclusivité dans le temps, le territoire et le secteur."),
            ("cession", "Vérifier l'étendue de la cession : supports, territoire, durée et finalités."),
            ("retard", "Vérifier les conséquences d'un retard client ou prestataire."),
            ("pénalité", "Vérifier si les pénalités sont plafonnées et proportionnées."),
            ("retouche", "Fixer le nombre de retours inclus et le tarif des demandes supplémentaires."),
            ("résiliation", "Vérifier les causes, le préavis et les conséquences financières de la résiliation."),
        ]
        found = [message for token, message in checks if token in text]
        if not found:
            st.info("Aucun mot-clé de vigilance détecté. Une lecture humaine reste nécessaire.")
        else:
            for item in found:
                st.warning(item)

with tabs[5]:
    st.header("Sauvegarde et restauration")
    export_data = {
        "version": 10,
        "exported_at": datetime.now().isoformat(),
        "briefs": st.session_state.briefs,
        "opportunities": st.session_state.opportunities,
        "coefficients": st.session_state.coefficients,
    }
    st.download_button(
        "Télécharger la sauvegarde JSON",
        json.dumps(export_data, ensure_ascii=False, indent=2),
        "manager_creatifs_sauvegarde.json",
        "application/json",
    )
    uploaded = st.file_uploader("Restaurer une sauvegarde JSON", type=["json"])
    if uploaded and st.button("Restaurer les données"):
        try:
            data = json.loads(uploaded.getvalue().decode("utf-8"))
            st.session_state.briefs = data.get("briefs", [])
            st.session_state.opportunities = data.get("opportunities", [])
            coeffs = data.get("coefficients")
            if isinstance(coeffs, dict) and all(k in coeffs for k in DEFAULT_COEFFICIENTS):
                st.session_state.coefficients = coeffs
            st.success("Données restaurées.")
            st.rerun()
        except Exception as exc:
            st.error(f"Sauvegarde invalide : {exc}")
