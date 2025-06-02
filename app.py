import streamlit as st
import vobject
import pandas as pd
import io

st.set_page_config(page_title="Éditeur de Contacts VCF", layout="wide")
st.title("📇 Éditeur de contacts VCF")

def clean_vcf_lines(file_content):
    lines = file_content.splitlines()
    clean_lines = []
    skip_mode = False
    for line in lines:
        if line.startswith("PHOTO") or line.startswith("LOGO"):
            skip_mode = True
            continue
        if skip_mode:
            if not line.startswith(" "):  # Fin du bloc encodé
                skip_mode = False
        if not skip_mode:
            clean_lines.append(line)
    return "\n".join(clean_lines)

def parse_vcf(file_content):
    contacts = []
    for vcard in vobject.readComponents(file_content, ignoreUnreadable=True):
        try:
            contact = {
                "Full Name": str(getattr(vcard, 'fn', {}).value) if hasattr(vcard, 'fn') else "",
                "Telephone": str(getattr(vcard, 'tel', {}).value) if hasattr(vcard, 'tel') else "",
                "Email": str(getattr(vcard, 'email', {}).value) if hasattr(vcard, 'email') else ""
            }
            contacts.append(contact)
        except Exception:
            continue
    return pd.DataFrame(contacts)

def export_to_vcf(df):
    output = io.StringIO()
    for _, row in df.iterrows():
        vcard = vobject.vCard()
        vcard.add('fn')
        vcard.fn.value = row['Full Name']
        if row['Telephone']:
            vcard.add('tel')
            vcard.tel.value = row['Telephone']
            vcard.tel.type_param = 'CELL'
        if row['Email']:
            vcard.add('email')
            vcard.email.value = row['Email']
            vcard.email.type_param = 'INTERNET'
        output.write(vcard.serialize())
    return output.getvalue()

# Upload du fichier
uploaded_file = st.file_uploader("Importer un fichier .vcf", type=["vcf"])

if uploaded_file:
    file_content = uploaded_file.read().decode("utf-8", errors="ignore")
    cleaned_content = clean_vcf_lines(file_content)
    df = parse_vcf(cleaned_content).fillna("")  # Pour éviter les NaN

    st.subheader("📋 Modifier les contacts")
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

    # Suppression
    if "deleted_rows" not in st.session_state:
        st.session_state.deleted_rows = []

    with st.form("edit_form"):
        index_to_delete = st.number_input("Index à supprimer (optionnel)", min_value=0, max_value=len(edited_df)-1, step=1)
        delete = st.form_submit_button("🗑 Supprimer le contact")
        if delete:
            st.session_state.deleted_rows.append(index_to_delete)
            st.success(f"Contact à l'index {index_to_delete} supprimé")

    final_df = edited_df.drop(st.session_state.deleted_rows, errors='ignore').reset_index(drop=True)

    st.subheader("✅ Contacts finaux")
    st.dataframe(final_df, use_container_width=True)

    vcf_output = export_to_vcf(final_df)
    st.download_button("💾 Télécharger le fichier VCF modifié", data=vcf_output, file_name="contacts_modifiés.vcf", mime="text/x-vcard")
