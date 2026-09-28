import json
import re
from datetime import datetime

import streamlit as st


st.set_page_config(
    page_title="ESN Artistique",
    page_icon="🎨",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 4rem;
        }

        .main-title {
            padding: 26px;
            border-radius: 18px;
            color: white;
            background: linear-gradient(135deg, #18354D, #25647A);
            margin-bottom: 22px;
        }

        .card {
            padding: 18px;
            border: 1px solid #DDE6EA;
            border-radius: 14px;
            background-color: white;
            margin-bottom: 12px;
        }

        .score {
            color: #0B7E76;
            font-size: 25px;
            font-weight: 800;
        }

        .good {
            color: #17735A;
            font-weight: 600;
        }

        .warning {
            color: #A75A20;
            font-weight: 600;
        }

        .small {
            color: #65727A;
            font-size: 14px;
        }

        div[data-testid="stMetric"] {
            border: 1px solid #DDE6EA;
            padding: 15px;
            border-radius: 12px;
            background-color: white;
        }

        .stButton > button {
            background-color: #18A99A;
            color: white;
            border: none;
            font-weight: 700;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------------------------------------------------
# État de l'application
# -------------------------------------------------------------------

if "talents" not in st.session_state:
    st.session_state.talents = []

if "briefs" not in st.session_state:
    st.session_state.briefs = []

if "opportunities" not in st.session_state:
    st.session_state.opportunities = []


# -------------------------------------------------------------------
# Fonctions
# -------------------------------------------------------------------

def normalize_tokens(value):
    """Transforme un texte en ensemble de mots comparables."""
    if not value:
        return set()

    return {
        token
        for token in re.split(r"[^a-zA-ZÀ-ÿ0-9]+", value.lower())
        if len(token) > 1
    }


def calculate_match(talent, brief):
    """
    Produit un score indicatif et explicable.
    Ce score reste une aide à la décision, pas une vérité artistique.
    """

    score = 0
    reasons = []
    gaps = []

    wanted_professions = normalize_tokens(brief.get("professions", ""))
    talent_professions = normalize_tokens(
        talent.get("profession", "") + " " + talent.get("skills", "")
    )

    profession_overlap = wanted_professions.intersection(talent_professions)

    if profession_overlap:
        score += 35
        reasons.append("Métier ou compétences compatibles avec le besoin.")
    else:
        gaps.append("Métier principal à vérifier.")

    wanted_styles = normalize_tokens(brief.get("styles", ""))
    talent_styles = normalize_tokens(talent.get("styles", ""))

    if wanted_styles:
        style_overlap = wanted_styles.intersection(talent_styles)
        style_ratio = len(style_overlap) / max(len(wanted_styles), 1)

        score += round(30 * style_ratio)

        if style_overlap:
            reasons.append(
                "Univers artistique compatible : "
                + ", ".join(sorted(style_overlap))
                + "."
            )
        else:
            gaps.append("Adéquation artistique à challenger.")
    else:
        score += 10
        reasons.append("Le brief artistique reste ouvert.")

    brief_location = brief.get("location", "").strip().lower()
    talent_location = talent.get("location", "").strip().lower()

    if brief_location and talent_location:
        if (
            brief_location in talent_location
            or talent_location in brief_location
        ):
            score += 15
            reasons.append("Zone géographique compatible.")
        else:
            gaps.append("Déplacement ou frais à confirmer.")

    budget = float(brief.get("budget", 0) or 0)
    rate = float(talent.get("rate", 0) or 0)

    if budget and rate:
        if rate <= budget:
            score += 15
            reasons.append("Tarif déclaré compatible avec l'enveloppe.")
        else:
            gaps.append("Tarif supérieur au budget déclaré.")

    availability = talent.get("availability", "").lower()

    if availability not in ["indisponible", "non disponible", "non"\]:
        score += 5
        reasons.append("Disponibilité potentielle, à confirmer.")
    else:
        gaps.append("Talent actuellement déclaré indisponible.")

    return {
        "score": min(score, 100),
        "reasons": reasons,
        "gaps": gaps,
    }


def generate_shortlist(brief, limit=3):
    """Classe les talents selon le brief."""

    results = []

    for talent in st.session_state.talents:
        match = calculate_match(talent, brief)

        results.append(
            {
                **talent,
                "match_score": match["score"],
                "match_reasons": match["reasons"],
                "match_gaps": match["gaps"],
            }
        )

    return sorted(
        results,
        key=lambda item: (
            item["match_score"],
            -float(item.get("rate", 0) or 0),
        ),
        reverse=True,
    )[:limit]


def calculate_talent_roi(
    service_cost,
    hours_saved,
    hourly_value,
    new_revenue,
    direct_costs,
    negotiation_gain,
):
    recovered_time_value = hours_saved * hourly_value
    mission_contribution = max(0, new_revenue - direct_costs)

    gross_value = (
        recovered_time_value
        + mission_contribution
        + negotiation_gain
    )

    net_gain = gross_value - service_cost

    roi = (
        (net_gain / service_cost) * 100
        if service_cost
        else 0
    )

    break_even_hours = (
        service_cost / hourly_value
        if hourly_value
        else 0
    )

    return {
        "recovered_time_value": recovered_time_value,
        "mission_contribution": mission_contribution,
        "gross_value": gross_value,
        "net_gain": net_gain,
        "roi": roi,
        "break_even_hours": break_even_hours,
    }


def calculate_client_roi(
    service_cost,
    hours_saved,
    hourly_cost,
    incident_cost_avoided,
    delay_value,
):
    time_value = hours_saved * hourly_cost

    gross_value = (
        time_value
        + incident_cost_avoided
        + delay_value
    )

    net_gain = gross_value - service_cost

    roi = (
        (net_gain / service_cost) * 100
        if service_cost
        else 0
    )

    return {
        "time_value": time_value,
        "gross_value": gross_value,
        "net_gain": net_gain,
        "roi": roi,
    }


def application_export():
    return {
        "exported_at": datetime.now().isoformat(),
        "talents": st.session_state.talents,
        "briefs": st.session_state.briefs,
        "opportunities": st.session_state.opportunities,
    }


# -------------------------------------------------------------------
# En-tête
# -------------------------------------------------------------------

st.markdown(
    """
    <div class="main-title">
        <h1>🎨 ESN Artistique</h1>
        <p>
            Gestion des talents, qualification des briefs,
            casting professionnel et calcul du ROI.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# -------------------------------------------------------------------
# Menu
# -------------------------------------------------------------------

tabs = st.tabs(
    [
        "📊 Tableau de bord",
        "👤 Talents",
        "📝 Briefs clients",
        "🎯 Matching",
        "💰 ROI",
        "💾 Sauvegarde",
    ]
)


# -------------------------------------------------------------------
# Tableau de bord
# -------------------------------------------------------------------

with tabs[0\]:
    st.subheader("Vue d'ensemble")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Talents enregistrés", len(st.session_state.talents))
    col2.metric("Briefs clients", len(st.session_state.briefs))
    col3.metric(
        "Briefs nouveaux",
        len(
            [
                brief
                for brief in st.session_state.briefs
                if brief.get("status") == "Nouveau"
            ]
        ),
    )
    col4.metric(
        "Opportunités",
        len(st.session_state.opportunities),
    )

    st.markdown("### Processus cible")

    st.info(
        """
        Demande entrante → qualification → création du brief →
        matching → validation humaine → devis → négociation →
        mission → reporting et calcul du ROI.
        """
    )

    st.warning(
        """
        L'application ne doit jamais accepter automatiquement une mission,
        fixer un prix définitif ou engager juridiquement un talent.
        Le choix artistique, le prix final et les engagements restent validés
        par une personne.
        """
    )

    if st.session_state.briefs:
        st.markdown("### Derniers briefs")

        for brief in reversed(st.session_state.briefs[-5:]):
            st.markdown(
                f"""
                <div class="card">
                    <strong>{brief["client"]}</strong>
                    <br>
                    {brief["project"]}
                    <div class="small">
                        {brief["professions"]} ·
                        Budget : {brief["budget"\]:.0f} € ·
                        Statut : {brief["status"]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# -------------------------------------------------------------------
# Talents
# -------------------------------------------------------------------

with tabs[1\]:
    st.subheader("Ajouter un talent")

    with st.form("talent_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            talent_name = st.text_input("Nom du talent *")
            talent_profession = st.text_input(
                "Métier *",
                placeholder="Photographe, vidéaste, monteur...",
            )
            talent_styles = st.text_input(
                "Univers artistiques",
                placeholder="Concert, premium, backstage, social-first...",
            )
            talent_skills = st.text_area(
                "Compétences",
                placeholder="Photo événementielle, montage, vidéo verticale...",
            )

        with col2:
            talent_location = st.text_input(
                "Zone géographique",
                placeholder="Paris, Lille, France...",
            )
            talent_rate = st.number_input(
                "Tarif indicatif par jour",
                min_value=0.0,
                step=50.0,
            )
            talent_availability = st.selectbox(
                "Disponibilité",
                [
                    "Disponible",
                    "À confirmer",
                    "Disponibilité partielle",
                    "Indisponible",
                ],
            )
            talent_portfolio = st.text_input(
                "Lien du portfolio"
            )

        talent_notes = st.text_area(
            "Notes internes",
            placeholder=(
                "Préférences, exclusions, clients historiques, "
                "contraintes particulières..."
            ),
        )

        add_talent = st.form_submit_button("Ajouter le talent")

        if add_talent:
            if not talent_name or not talent_profession:
                st.error("Le nom et le métier sont obligatoires.")
            else:
                st.session_state.talents.append(
                    {
                        "id": len(st.session_state.talents) + 1,
                        "name": talent_name,
                        "profession": talent_profession,
                        "styles": talent_styles,
                        "skills": talent_skills,
                        "location": talent_location,
                        "rate": talent_rate,
                        "availability": talent_availability,
                        "portfolio": talent_portfolio,
                        "notes": talent_notes,
                    }
                )

                st.success("Talent ajouté au vivier.")

    st.divider()
    st.subheader("Vivier actuel")

    if not st.session_state.talents:
        st.info("Aucun talent enregistré pour le moment.")

    for index, talent in enumerate(st.session_state.talents):
        with st.expander(
            f'{talent["name"]} · {talent["profession"]}'
        ):
            col1, col2 = st.columns(2)

            with col1:
                st.write("**Styles :**", talent["styles"] or "Non renseigné")
                st.write(
                    "**Compétences :**",
                    talent["skills"] or "Non renseigné",
                )
                st.write(
                    "**Localisation :**",
                    talent["location"] or "Non renseignée",
                )

            with col2:
                st.write(
                    "**Tarif indicatif :**",
                    f'{talent["rate"\]:.0f} €',
                )
                st.write(
                    "**Disponibilité :**",
                    talent["availability"],
                )

                if talent["portfolio"\]:
                    st.markdown(
                        f'{talent["portfolio"]}'
                    )

            st.write(
                "**Notes :**",
                talent["notes"] or "Aucune note.",
            )

            if st.button(
                "Supprimer ce talent",
                key=f"delete_talent_{index}",
            ):
                st.session_state.talents.pop(index)
                st.rerun()


# -------------------------------------------------------------------
# Briefs
# -------------------------------------------------------------------

with tabs[2\]:
    st.subheader("Créer un brief client")

    with st.form("brief_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            brief_client = st.text_input("Client *")
            brief_project = st.text_input("Nom du projet *")
            brief_professions = st.text_input(
                "Métiers recherchés",
                placeholder="Photographe, vidéaste...",
            )
            brief_styles = st.text_input(
                "Univers souhaités",
                placeholder="Concert, cinématique, social-first...",
            )
            brief_location = st.text_input(
                "Lieu ou zone géographique"
            )

        with col2:
            brief_budget = st.number_input(
                "Budget disponible",
                min_value=0.0,
                step=100.0,
            )
            brief_deadline = st.text_input(
                "Date ou échéance"
            )
            brief_status = st.selectbox(
                "Statut",
                [
                    "Nouveau",
                    "À qualifier",
                    "Short-list",
                    "Devis",
                    "Négociation",
                    "Signé",
                    "Perdu",
                ],
            )
            brief_source = st.selectbox(
                "Origine",
                [
                    "Demande entrante",
                    "Mission apportée",
                    "Client historique du talent",
                    "Extension de mission",
                    "Prospection",
                ],
            )

        brief_deliverables = st.text_area(
            "Livrables attendus",
            placeholder=(
                "Photos, vidéos verticales, backstage, "
                "montage, nombre de versions..."
            ),
        )

        brief_rights = st.text_area(
            "Diffusion et droits demandés",
            placeholder=(
                "Réseaux sociaux, publicité, territoire, durée, exclusivité..."
            ),
        )

        brief_notes = st.text_area(
            "Informations complémentaires"
        )

        add_brief = st.form_submit_button("Enregistrer le brief")

        if add_brief:
            if not brief_client or not brief_project:
                st.error(
                    "Le client et le nom du projet sont obligatoires."
                )
            else:
                st.session_state.briefs.append(
                    {
                        "id": len(st.session_state.briefs) + 1,
                        "client": brief_client,
                        "project": brief_project,
                        "professions": brief_professions,
                        "styles": brief_styles,
                        "location": brief_location,
                        "budget": brief_budget,
                        "deadline": brief_deadline,
                        "status": brief_status,
                        "source": brief_source,
                        "deliverables": brief_deliverables,
                        "rights": brief_rights,
                        "notes": brief_notes,
                        "created_at": datetime.now().isoformat(),
                    }
                )

                st.success("Brief client enregistré.")

    st.divider()
    st.subheader("Briefs enregistrés")

    if not st.session_state.briefs:
        st.info("Aucun brief enregistré pour le moment.")

    for index, brief in enumerate(st.session_state.briefs):
        with st.expander(
            f'{brief["client"]} · {brief["project"]} · {brief["status"]}'
        ):
            st.write(
                "**Métiers recherchés :**",
                brief["professions"] or "Non renseignés",
            )
            st.write(
                "**Univers souhaités :**",
                brief["styles"] or "Non renseignés",
            )
            st.write(
                "**Budget :**",
                f'{brief["budget"\]:.0f} €',
            )
            st.write(
                "**Lieu :**",
                brief["location"] or "Non renseigné",
            )
            st.write(
                "**Échéance :**",
                brief["deadline"] or "Non renseignée",
            )
            st.write(
                "**Origine :**",
                brief["source"],
            )
            st.write(
                "**Livrables :**",
                brief["deliverables"] or "Non renseignés",
            )
            st.write(
                "**Diffusion et droits :**",
                brief["rights"] or "Non renseignés",
            )

            if st.button(
                "Supprimer ce brief",
                key=f"delete_brief_{index}",
            ):
                st.session_state.briefs.pop(index)
                st.rerun()


# -------------------------------------------------------------------
# Matching
# -------------------------------------------------------------------

with tabs[3\]:
    st.subheader("Matching et short-list")

    if not st.session_state.briefs:
        st.info("Commence par créer un brief client.")

    elif not st.session_state.talents:
        st.info("Commence par enregistrer des talents.")

    else:
        brief_options = {
            f'{brief["client"]} · {brief["project"]}': brief
            for brief in st.session_state.briefs
        }

        selected_brief_label = st.selectbox(
            "Choisir le brief",
            list(brief_options.keys()),
        )

        selected_brief = brief_options[selected_brief_label]

        number_of_profiles = st.slider(
            "Nombre de profils à présenter",
            min_value=1,
            max_value=min(5, len(st.session_state.talents)),
            value=min(3, len(st.session_state.talents)),
        )

        shortlist = generate_shortlist(
            selected_brief,
            number_of_profiles,
        )

        st.markdown("### Résumé du besoin")

        st.write(
            f'**Client :** {selected_brief["client"]}'
        )
        st.write(
            f'**Projet :** {selected_brief["project"]}'
        )
        st.write(
            f'**Métiers :** {selected_brief["professions"]}'
        )
        st.write(
            f'**Styles :** {selected_brief["styles"]}'
        )
        st.write(
            f'**Budget :** {selected_brief["budget"\]:.0f} €'
        )

        st.warning(
            """
            Le score est un indicateur de présélection.
            Il ne constitue pas un jugement absolu sur la qualité artistique.
            La décision finale doit rester contextualisée et humaine.
            """
        )

        st.markdown("### Short-list proposée")

        for position, talent in enumerate(shortlist, start=1):
            st.markdown(
                f"""
                <div class="card">
                    <div class="score">
                        Profil {position} · {talent["match_score"]}/100
                    </div>
                    <h3>{talent["name"]}</h3>
                    <p>
                        {talent["profession"]} ·
                        {talent["location"] or "Zone non renseignée"} ·
                        {talent["rate"\]:.0f} €
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            col1, col2 = st.columns(2)

            with col1:
                st.markdown(
                    '<div class="good">Pourquoi ce profil</div>',
                    unsafe_allow_html=True,
                )

                for reason in talent["match_reasons"\]:
                    st.write("✅", reason)

            with col2:
                st.markdown(
                    '<div class="warning">Points à vérifier</div>',
                    unsafe_allow_html=True,
                )

                if talent["match_gaps"\]:
                    for gap in talent["match_gaps"\]:
                        st.write("⚠️", gap)
                else:
                    st.write("Aucun écart principal détecté.")

            if talent["portfolio"\]:
                st.markdown(
                    f'{talent["portfolio"]}'
                )

            st.divider()


# -------------------------------------------------------------------
# ROI
# -------------------------------------------------------------------

with tabs[4\]:
    roi_talent_tab, roi_client_tab = st.tabs(
        ["ROI du talent", "ROI du client final"]
    )

    with roi_talent_tab:
        st.subheader("Simulateur ROI talent")

        col1, col2 = st.columns(2)

        with col1:
            talent_service_cost = st.number_input(
                "Coût mensuel du service",
                min_value=0.0,
                value=350.0,
                step=10.0,
                key="talent_service_cost",
            )
            talent_hours_saved = st.number_input(
                "Heures économisées",
                min_value=0.0,
                value=6.0,
                step=1.0,
            )
            talent_hourly_value = st.number_input(
                "Valeur d'une heure du talent",
                min_value=0.0,
                value=50.0,
                step=5.0,
            )

        with col2:
            talent_new_revenue = st.number_input(
                "Chiffre d'affaires nouveau",
                min_value=0.0,
                value=2500.0,
                step=100.0,
            )
            talent_direct_costs = st.number_input(
                "Coûts directs de la mission",
                min_value=0.0,
                value=500.0,
                step=100.0,
            )
            talent_negotiation_gain = st.number_input(
                "Gain obtenu par la négociation",
                min_value=0.0,
                value=0.0,
                step=50.0,
            )

        talent_result = calculate_talent_roi(
            talent_service_cost,
            talent_hours_saved,
            talent_hourly_value,
            talent_new_revenue,
            talent_direct_costs,
            talent_negotiation_gain,
        )

        metric1, metric2, metric3, metric4 = st.columns(4)

        metric1.metric(
            "Valeur brute",
            f'{talent_result["gross_value"\]:.0f} €',
        )
        metric2.metric(
            "Gain net",
            f'{talent_result["net_gain"\]:.0f} €',
        )
        metric3.metric(
            "ROI",
            f'{talent_result["roi"\]:.1f} %',
        )
        metric4.metric(
            "Seuil de rentabilité",
            f'{talent_result["break_even_hours"\]:.1f} h',
        )

        st.caption(
            """
            Simulation indicative. Les hypothèses doivent être remplacées
            par les données réelles du talent.
            """
        )

    with roi_client_tab:
        st.subheader("Simulateur ROI client final")

        col1, col2 = st.columns(2)

        with col1:
            client_service_cost = st.number_input(
                "Honoraires du casting ou de la coordination",
                min_value=0.0,
                value=350.0,
                step=10.0,
            )
            client_hours_saved = st.number_input(
                "Heures internes évitées",
                min_value=0.0,
                value=10.0,
                step=1.0,
            )
            client_hourly_cost = st.number_input(
                "Coût horaire chargé",
                min_value=0.0,
                value=60.0,
                step=5.0,
            )

        with col2:
            client_incident_cost = st.number_input(
                "Coût d'incident évité",
                min_value=0.0,
                value=0.0,
                step=100.0,
            )
            client_delay_value = st.number_input(
                "Valeur d'un délai réduit",
                min_value=0.0,
                value=0.0,
                step=100.0,
            )

        client_result = calculate_client_roi(
            client_service_cost,
            client_hours_saved,
            client_hourly_cost,
            client_incident_cost,
            client_delay_value,
        )

        metric1, metric2, metric3 = st.columns(3)

        metric1.metric(
            "Valeur brute",
            f'{client_result["gross_value"\]:.0f} €',
        )
        metric2.metric(
            "Gain net",
            f'{client_result["net_gain"\]:.0f} €',
        )
        metric3.metric(
            "ROI",
            f'{client_result["roi"\]:.1f} %',
        )

        st.caption(
            """
            Le coût d'incident évité et la valeur du délai réduit ne doivent
            être utilisés que si le client accepte et valide ces hypothèses.
            """
        )


# -------------------------------------------------------------------
# Sauvegarde et restauration
# -------------------------------------------------------------------

with tabs[5\]:
    st.subheader("Sauvegarder les données")

    st.warning(
        """
   ge régulièrement une sauvegarde JSON pour éviter
        de perdre tes talents et tes briefs.
        """
    )

    export_data = application_export()
    export_json = json.dumps(
        export_data,
        ensure_ascii=False,
        indent=2,
    )

    st.download_button(
        label="Télécharger la sauvegarde",
        data=export_json,
        file_name="esn_artistique_sauvegarde.json",
        mime="application/json",
    )

    st.divider()
    st.subheader("Restaurer une sauvegarde")

    uploaded_file = st.file_uploader(
        "Importer un fichier JSON",
        type=["json"],
    )

    if uploaded_file is not None:
        try:
            restored_data = json.load(uploaded_file)

            st.session_state.talents = restored_data.get(
                "talents",
                [],
            )
            st.session_state.briefs = restored_data.get(
                "briefs",
                [],
            )
            st.session_state.opportunities = restored_data.get(
                "opportunities",
                [],
            )

            st.success("Sauvegarde restaurée.")
        except Exception as error:
            st.error(
                f"Impossible de restaurer le fichier : {error}"
            )

    st.divider()

    if st.button("Effacer toutes les données"):
        st.session_state.talents = []
        st.session_state.briefs = []
        st.session_state.opportunities = []
        st.success("Toutes les données ont été effacées.")
        st.rerun()
