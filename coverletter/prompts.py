"""
Covering letter generation prompts for Claude API.
Contains sample-based templates for tourist and business visa covering letters.
"""

SYSTEM_PROMPT = """You are an expert visa covering letter writer for a travel consulting firm.
You generate professional, formal covering letters for visa applications.
You MUST output ONLY the letter text — no commentary, no markdown, no explanations before or after.
Use proper formal English. Be concise but thorough. Match the tone and structure of the samples provided."""


TOURIST_SCHENGEN_PROMPT = """Generate a covering letter for a SCHENGEN TOURIST VISA application.
Follow this exact structure and tone, based on this proven sample format:

STRUCTURE:
1. Date (top left)
2. "To," then "The Visa Officer" then "Consulate General of [Country]" then City
3. "Subject: Request for Issuance of Schengen Tourist Visa"
4. "Dear Sir/Madam,"
5. Opening paragraph: "I, the undersigned, [Title]. [Full Name], holding Indian Passport No. [Passport No.], ..." — state intent to travel, mention co-travelers if any
6. Tour details paragraph: Tour operator name, what's included (flights, hotels, meals, sightseeing), exact travel dates, duration
7. Country-wise itinerary: List each Schengen country with dates and nights. Format: "[Country]: [dates] ([X] night(s)) – [Cities]"
8. Consulate justification paragraph: Explain why applying at THIS consulate (longest stay / first major destination)
9. Entry point and visa request: First Schengen entry point, date, request visa validity
10. Financial standing paragraph: Employment/retirement status, savings (FDs, etc.), sponsorship details if applicable
11. Closing: "The purpose of our visit is purely tourism..." + documents enclosed + request to process
12. Contact information offer
13. "Thank you for your consideration."
14. "Yours sincerely," + Full Name + Passport No. + Contact + Email

IMPORTANT RULES:
- If there are co-travelers (spouse, family), mention them with full name and passport number in the opening
- Always include country-wise itinerary with exact dates and nights
- Always justify why applying at this particular consulate
- Always mention financial standing and who bears expenses
- Keep formal but warm tone
- Use "we" when there are co-travelers, "I" for solo travelers

Here are the applicant details to use:
{applicant_details}

Additional details provided by the visa executive:
{additional_details}

Generate the complete covering letter now. Output ONLY the letter text."""


BUSINESS_SCHENGEN_PROMPT = """Generate a covering letter for a SCHENGEN BUSINESS VISA application.
This letter is written by the EMPLOYER (company), NOT by the traveler personally.
Follow this exact structure and tone, based on proven sample formats:

STRUCTURE:
1. Date (top left)
2. "To," then "The Visa Officer" then "Consulate General of [Country]" then City
3. "Dear Sir,"
4. "Sub: Multiple Entry Visa to [Country] for business purpose."
5. Opening paragraph: "We have business relationship with [Foreign Company Name and full address/registration]. In this connection, we are deputing our employee, [Title]. [Full Name] for attending [purpose - business meetings/technical discussions/etc.]. The present schedule is fixed [start date] to [end date]."
6. Passport details in a structured format:
   Name: [Title]. [Full Name]
   Passport No.: [Number]
   Date of Birth: [DOB]
   Date & Place of issue: [Date], [Place]
   Valid up to: [Expiry Date]
7. Expense confirmation: "We confirm that the entire expenditure pertaining to the visit of our above employee to [Country] shall be borne by our Company."
8. Visa type request: "We request you to kindly issue Multiple Entry Business Visa valid for [duration], as our above official would need to visit [Country] regularly at short notices."
9. Documents enclosure line
10. "Thanking you,"
11. "Yours faithfully,"
12. "For [COMPANY NAME],"
13. Signatory Name + Designation
14. Company footer (address, phone, website, CIN if applicable)

IMPORTANT RULES:
- Written in THIRD PERSON from the company's perspective ("we are deputing our employee")
- Always mention the foreign business entity with full details
- Always include structured passport details
- Always confirm company sponsorship of expenses
- Keep formal corporate tone
- Signatory should be a senior official (GM, VP, Director level)

Here are the applicant/employee details:
{applicant_details}

Additional details provided by the visa executive:
{additional_details}

Generate the complete covering letter now. Output ONLY the letter text."""


BUSINESS_UK_PROMPT = """Generate a covering letter for a UK BUSINESS VISA application.
This letter is written by the EMPLOYER (company), NOT by the traveler personally.
Follow this exact structure and tone, based on proven sample formats:

STRUCTURE:
1. "Covering letter" as title (optional)
2. "To" (right-aligned or left) + Date
3. "The Visa officer" then "British High Commission" then City
4. "Sub: Business visa request for [Title]. [Full Name] holding passport No ([Passport No.])"
5. "Dear Sir/Madam,"
6. Company introduction paragraph: Brief about the company (what it does, parent company if subsidiary, locations, functions)
7. Purpose paragraph: "[Name] ([Designation]) is required to visit [UK office address] to attend business meetings from [start date] to [end date]"
8. Travel compliance paragraph (optional): vaccination/safety compliance acknowledgment
9. Visa applicant details:
   Full name: [Title]. [Full Name]
   Date of birth: [DOB]
   Nationality: [Nationality]
   Passport no: [Number]
   Passport expiry: [Expiry]
10. Contact offer: "Please do not hesitate to contact me on [email] if you have any further queries..."
11. "I request you to kindly grant the necessary visa."
12. "Thanking You"
13. "With Warm Regards"
14. Signatory Name + Designation + Company Name

IMPORTANT RULES:
- Written by HR/General Affairs, not the traveler
- Include brief company description (especially if subsidiary/GCC)
- Mention specific UK office address being visited
- Keep formal but slightly warmer tone than Schengen business letters
- Include applicant details in labeled list format

Here are the applicant/employee details:
{applicant_details}

Additional details provided by the visa executive:
{additional_details}

Generate the complete covering letter now. Output ONLY the letter text."""


TOURIST_UK_PROMPT = """Generate a covering letter for a UK TOURIST VISA application.
Follow this structure for a personal tourist visa covering letter:

STRUCTURE:
1. Date
2. "To," then "The Visa Officer" then "British High Commission" then City
3. "Subject: Request for UK Tourist Visa"
4. "Dear Sir/Madam,"
5. Introduction: Self-introduction with name, passport number, purpose (tourism/visiting family/sightseeing)
6. Travel details: Dates of travel, duration, places to visit in the UK
7. Accommodation: Hotel bookings or host details (if visiting family/friends, include their address and immigration status)
8. Financial standing: Employment details, income, savings, who bears expenses
9. Ties to home country: Property, family, job — reasons to return
10. Documents enclosed
11. Contact details
12. "Thank you for your consideration."
13. "Yours sincerely," + Name + Passport + Contact

Here are the applicant details:
{applicant_details}

Additional details provided by the visa executive:
{additional_details}

Generate the complete covering letter now. Output ONLY the letter text."""


def get_prompt(visa_type, visa_purpose):
    """Return the appropriate prompt template based on visa type and purpose."""
    key = f"{visa_purpose.lower()}_{visa_type.lower()}"
    prompts = {
        'tourist_schengen': TOURIST_SCHENGEN_PROMPT,
        'tourist_uk': TOURIST_UK_PROMPT,
        'business_schengen': BUSINESS_SCHENGEN_PROMPT,
        'business_uk': BUSINESS_UK_PROMPT,
    }
    # Default fallbacks
    if key not in prompts:
        if visa_purpose.lower() == 'business':
            return BUSINESS_SCHENGEN_PROMPT
        return TOURIST_SCHENGEN_PROMPT
    return prompts[key]
