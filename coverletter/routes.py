"""
Covering Letter Generator routes for VisaDesk.
Uses Claude API to generate professional covering letters based on
applicant data and visa executive input.
"""
import os
import json
import re
from datetime import datetime
from flask import (Blueprint, render_template, request, jsonify, flash,
                   redirect, url_for, current_app, send_file)
from flask_login import login_required, current_user
from extensions import db
from models import Applicant
from .prompts import get_prompt, SYSTEM_PROMPT

coverletter_bp = Blueprint('coverletter', __name__, url_prefix='/coverletter')


def call_claude_api(system_prompt, user_prompt):
    """Call Claude API to generate covering letter text.
    Uses the anthropic Python SDK."""
    import anthropic

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise ValueError(
            'ANTHROPIC_API_KEY not set. Please set it in your environment '
            'or .env file. Get your key from https://console.anthropic.com/'
        )

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    return message.content[0].text


def format_applicant_details(applicant):
    """Format applicant record into a clean text block for the AI prompt."""
    lines = []
    lines.append(f"Full Name: {applicant.full_name}")
    if applicant.surname:
        lines.append(f"Surname: {applicant.surname}")
    if applicant.given_names:
        lines.append(f"Given Names: {applicant.given_names}")
    if applicant.passport_number:
        lines.append(f"Passport Number: {applicant.passport_number}")
    if applicant.nationality:
        lines.append(f"Nationality: {applicant.nationality}")
    if applicant.sex:
        lines.append(f"Sex: {applicant.sex}")
    if applicant.date_of_birth:
        lines.append(f"Date of Birth: {applicant.date_of_birth.strftime('%d/%m/%Y')}")
    if applicant.place_of_birth:
        lines.append(f"Place of Birth: {applicant.place_of_birth}")
    if applicant.passport_issue_date:
        lines.append(f"Passport Issue Date: {applicant.passport_issue_date.strftime('%d/%m/%Y')}")
    if applicant.passport_expiry_date:
        lines.append(f"Passport Expiry Date: {applicant.passport_expiry_date.strftime('%d/%m/%Y')}")
    if applicant.date_of_travel:
        lines.append(f"Date of Travel: {applicant.date_of_travel.strftime('%d/%m/%Y')}")
    if applicant.destination_country:
        lines.append(f"Destination Country: {applicant.destination_country}")
    if applicant.visa_type:
        lines.append(f"Visa Type: {applicant.visa_type}")
    if applicant.visa_purpose:
        lines.append(f"Visa Purpose: {applicant.visa_purpose}")
    if applicant.client_type:
        lines.append(f"Client Type: {applicant.client_type}")
    if applicant.corporate_name:
        lines.append(f"Corporate/Company Name: {applicant.corporate_name}")

    return '\n'.join(lines)


def generate_docx_from_text(letter_text, applicant_name):
    """Generate a .docx file from the covering letter text.
    Returns the file path."""
    import subprocess
    import tempfile

    # Create a temporary directory for the output
    output_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], '_coverletter')
    os.makedirs(output_dir, exist_ok=True)

    # Clean filename
    safe_name = re.sub(r'[^A-Za-z0-9_]', '_', applicant_name)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"Covering_Letter_{safe_name}_{timestamp}.docx"
    output_path = os.path.join(output_dir, filename)

    # Use docx-js via Node.js to create the DOCX
    js_code = _build_docx_js(letter_text, applicant_name)

    js_path = os.path.join(output_dir, f'_temp_{timestamp}.js')
    with open(js_path, 'w') as f:
        f.write(js_code)

    try:
        result = subprocess.run(
            ['node', js_path],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, 'DOCX_OUTPUT': output_path}
        )
        if result.returncode != 0:
            raise RuntimeError(f"DOCX generation failed: {result.stderr}")
    finally:
        try:
            os.remove(js_path)
        except Exception:
            pass

    return output_path, filename


def _build_docx_js(letter_text, title):
    """Build a Node.js script that creates a DOCX from the letter text."""
    # Escape the text for JS string
    escaped = letter_text.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')

    return f'''
const {{ Document, Packer, Paragraph, TextRun, AlignmentType,
         Header, Footer, PageNumber, BorderStyle }} = require("docx");
const fs = require("fs");

const outputPath = process.env.DOCX_OUTPUT;
const letterText = `{escaped}`;

// Split into paragraphs
const paragraphs = letterText.split("\\n");

const children = [];
for (const line of paragraphs) {{
    const trimmed = line.trim();

    // Detect heading-like lines (Subject:, Sub:, Dear, To,)
    const isBold = /^(Subject:|Sub:|Dear |To,|Yours |Thanking |Thank you|With Warm|For [A-Z])/.test(trimmed);
    const isSignature = /^(Yours |Thanking |Thank you|With Warm)/.test(trimmed);

    children.push(
        new Paragraph({{
            spacing: {{ after: trimmed === "" ? 120 : 80 }},
            children: [
                new TextRun({{
                    text: trimmed,
                    font: "Arial",
                    size: 22, // 11pt
                    bold: isBold,
                }})
            ]
        }})
    );
}}

const doc = new Document({{
    styles: {{
        default: {{
            document: {{
                run: {{ font: "Arial", size: 22 }}
            }}
        }}
    }},
    sections: [{{
        properties: {{
            page: {{
                size: {{ width: 12240, height: 15840 }},
                margin: {{ top: 1440, right: 1440, bottom: 1440, left: 1440 }}
            }}
        }},
        children: children
    }}]
}});

Packer.toBuffer(doc).then(buffer => {{
    fs.writeFileSync(outputPath, buffer);
    console.log("DOCX created: " + outputPath);
}});
'''


@coverletter_bp.route('/generate/<int:applicant_id>', methods=['GET', 'POST'])
@login_required
def generate(applicant_id):
    """Generate covering letter for an applicant."""
    applicant = Applicant.query.get_or_404(applicant_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('You do not have access to this applicant.', 'danger')
        return redirect(url_for('applicants.list_applicants'))

    if request.method == 'POST':
        # Get form inputs
        visa_type = request.form.get('visa_type', 'schengen').strip()
        visa_purpose = request.form.get('visa_purpose', applicant.visa_purpose or 'tourist').strip()
        consulate_city = request.form.get('consulate_city', '').strip()
        consulate_country = request.form.get('consulate_country', applicant.destination_country or '').strip()
        additional_details = request.form.get('additional_details', '').strip()

        # Build the additional details block from form fields
        extra_lines = []
        if consulate_city:
            extra_lines.append(f"Consulate City: {consulate_city}")
        if consulate_country:
            extra_lines.append(f"Consulate/Embassy Country: {consulate_country}")

        # Business-specific fields
        if visa_purpose.lower() == 'business':
            company_name = request.form.get('company_name', applicant.corporate_name or '').strip()
            company_address = request.form.get('company_address', '').strip()
            foreign_company = request.form.get('foreign_company', '').strip()
            foreign_company_address = request.form.get('foreign_company_address', '').strip()
            visit_purpose = request.form.get('visit_purpose', '').strip()
            signatory_name = request.form.get('signatory_name', '').strip()
            signatory_designation = request.form.get('signatory_designation', '').strip()
            travel_end_date = request.form.get('travel_end_date', '').strip()

            if company_name:
                extra_lines.append(f"Employer/Sending Company: {company_name}")
            if company_address:
                extra_lines.append(f"Company Address: {company_address}")
            if foreign_company:
                extra_lines.append(f"Foreign Company/Host: {foreign_company}")
            if foreign_company_address:
                extra_lines.append(f"Foreign Company Address: {foreign_company_address}")
            if visit_purpose:
                extra_lines.append(f"Specific Purpose of Visit: {visit_purpose}")
            if signatory_name:
                extra_lines.append(f"Letter Signatory Name: {signatory_name}")
            if signatory_designation:
                extra_lines.append(f"Signatory Designation: {signatory_designation}")
            if travel_end_date:
                extra_lines.append(f"Travel End Date: {travel_end_date}")

        # Tourist-specific fields
        if visa_purpose.lower() == 'tourist':
            tour_operator = request.form.get('tour_operator', '').strip()
            co_travelers = request.form.get('co_travelers', '').strip()
            itinerary = request.form.get('itinerary', '').strip()
            accommodation = request.form.get('accommodation', '').strip()
            financial_info = request.form.get('financial_info', '').strip()
            travel_end_date = request.form.get('travel_end_date', '').strip()

            if tour_operator:
                extra_lines.append(f"Tour Operator: {tour_operator}")
            if co_travelers:
                extra_lines.append(f"Co-travelers: {co_travelers}")
            if itinerary:
                extra_lines.append(f"Itinerary Details:\n{itinerary}")
            if accommodation:
                extra_lines.append(f"Accommodation Details: {accommodation}")
            if financial_info:
                extra_lines.append(f"Financial Information: {financial_info}")
            if travel_end_date:
                extra_lines.append(f"Travel End Date: {travel_end_date}")

        if additional_details:
            extra_lines.append(f"Other Notes: {additional_details}")

        # Today's date for the letter
        extra_lines.append(f"Today's Date (for the letter): {datetime.now().strftime('%d %B %Y')}")

        all_additional = '\n'.join(extra_lines)

        # Get the right prompt template
        prompt_template = get_prompt(visa_type, visa_purpose)
        applicant_details = format_applicant_details(applicant)

        user_prompt = prompt_template.format(
            applicant_details=applicant_details,
            additional_details=all_additional
        )

        try:
            # Call Claude API
            letter_text = call_claude_api(SYSTEM_PROMPT, user_prompt)

            # Return the generated text via AJAX
            return jsonify({
                'success': True,
                'letter_text': letter_text,
                'applicant_name': applicant.full_name,
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    # GET — show the generation form
    return render_template('coverletter/generate.html', applicant=applicant)


@coverletter_bp.route('/download', methods=['POST'])
@login_required
def download_docx():
    """Download the generated covering letter as a DOCX file."""
    letter_text = request.form.get('letter_text', '')
    applicant_name = request.form.get('applicant_name', 'Applicant')

    if not letter_text:
        flash('No letter content to download.', 'warning')
        return redirect(url_for('applicants.list_applicants'))

    try:
        output_path, filename = generate_docx_from_text(letter_text, applicant_name)
        return send_file(
            output_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
    except Exception as e:
        flash(f'Error generating DOCX: {str(e)}. You can copy the text manually.', 'danger')
        return redirect(url_for('applicants.list_applicants'))
