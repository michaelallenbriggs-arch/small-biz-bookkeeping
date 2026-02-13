# app/categories/mappings.py
from __future__ import annotations

from typing import Dict, List


# ============================================================================

# COMPREHENSIVE VENDOR CATEGORY MAPPINGS

# Copy this entire block and paste into your VENDOR_CATEGORY_MAP in mappings.py

# ============================================================================

VENDOR_CATEGORY_MAP: Dict[str, str] = {
# ========================================================================
# AUTO & TRUCK (Mechanics, Auto Parts, Service)
# ======================================================================== ```
    # Auto Parts Stores
    "AutoZone": "Car & Truck",
    "Advance Auto Parts": "Car & Truck",
    "O'Reilly Auto Parts": "Car & Truck",
    "NAPA Auto Parts": "Car & Truck",
    "Pep Boys": "Car & Truck",
    "Autozone": "Car & Truck",
    "O'Reilly": "Car & Truck",
    "NAPA": "Car & Truck",

    # Auto Service & Repair
    "Jiffy Lube": "Car & Truck",
    "Valvoline": "Car & Truck",
    "Meineke": "Car & Truck",
    "Midas": "Car & Truck",
    "Firestone": "Car & Truck",
    "Goodyear": "Car & Truck",
    "Discount Tire": "Car & Truck",
    "Tire Discounters": "Car & Truck",
    "Monro": "Car & Truck",
    "Mavis Tire": "Car & Truck",
    "Big O Tires": "Car & Truck",
    "Les Schwab": "Car & Truck",
    "Pep Boys Auto": "Car & Truck",
    "Aamco": "Car & Truck",
    "Christian Brothers Automotive": "Car & Truck",
    "Grease Monkey": "Car & Truck",
    "Take 5 Oil Change": "Car & Truck",
    "Valvoline Instant Oil Change": "Car & Truck",
    "Precision Tune Auto Care": "Car & Truck",
    "Tuffy": "Car & Truck",
    "Mr. Tire": "Car & Truck",

    # Dealership Service Centers (common chains)
    "Caliber Collision": "Car & Truck",
    "Gerber Collision": "Car & Truck",
    "Maaco": "Car & Truck",
    "ABRA Auto": "Car & Truck",
    "Service King": "Car & Truck",

    # Auto Supplies & Equipment
    "Harbor Freight": "Car & Truck",
    "Northern Tool": "Car & Truck",
    "Tractor Supply": "Car & Truck",
    "Tractor Supply Co": "Car & Truck",
    "TSC": "Car & Truck",

    # Car Wash & Detailing
    "Car Wash": "Car & Truck",
    "Auto Spa": "Car & Truck",
    "Detail Shop": "Car & Truck",
    "Wash & Go": "Car & Truck",

    # ========================================================================
    # FUEL
    # ========================================================================

    "Shell": "Fuel",
    "Exxon": "Fuel",
    "Chevron": "Fuel",
    "BP": "Fuel",
    "Mobil": "Fuel",
    "Texaco": "Fuel",
    "Sunoco": "Fuel",
    "Marathon": "Fuel",
    "Speedway": "Fuel",
    "Circle K": "Fuel",
    "7-Eleven": "Fuel",
    "Wawa": "Fuel",
    "Sheetz": "Fuel",
    "QuikTrip": "Fuel",
    "RaceTrac": "Fuel",
    "Love's": "Fuel",
    "Pilot": "Fuel",
    "Flying J": "Fuel",
    "TA": "Fuel",
    "Travel Centers of America": "Fuel",
    "Petro": "Fuel",
    "Costco Gas": "Fuel",
    "Sam's Club Gas": "Fuel",
    "BJ's Gas": "Fuel",
    "Arco": "Fuel",
    "Phillips 66": "Fuel",
    "Conoco": "Fuel",
    "Valero": "Fuel",
    "Casey's": "Fuel",
    "GetGo": "Fuel",
    "Kum & Go": "Fuel",
    "Kwik Trip": "Fuel",
    "Murphy USA": "Fuel",
    "Gulf": "Fuel",
    "Citgo": "Fuel",

    # ========================================================================
    # LANDSCAPING & GROUNDS MAINTENANCE
    # ========================================================================

    # Home Improvement & Garden Centers
    "Home Depot": "Repairs & Maintenance",
    "Lowe's": "Repairs & Maintenance",
    "Menards": "Repairs & Maintenance",
    "Ace Hardware": "Repairs & Maintenance",
    "True Value": "Repairs & Maintenance",
    "Do it Best": "Repairs & Maintenance",

    # Landscaping Supplies & Equipment
    "SiteOne Landscape Supply": "Supplies",
    "SiteOne": "Supplies",
    "Ewing Irrigation": "Supplies",
    "Horizon Distributors": "Supplies",
    "BrightView": "Supplies",
    "John Deere Landscapes": "Supplies",
    "Target Specialty Products": "Supplies",

    # Nurseries & Garden Centers
    "Pike Nursery": "Supplies",
    "Armstrong Garden Centers": "Supplies",
    "Green Thumb Nursery": "Supplies",
    "Calloway's Nursery": "Supplies",

    # Lawn & Garden Equipment
    "The Home Depot Pro": "Equipment",
    "Tractor Supply": "Equipment",
    "Rural King": "Equipment",
    "Blain's Farm & Fleet": "Equipment",
    "Fleet Farm": "Equipment",

    # Mulch, Stone, Soil Suppliers
    "Mulch Express": "Supplies",
    "Landscape Supply": "Supplies",
    "Stone Center": "Supplies",

    # Irrigation
    "Sprinkler Warehouse": "Supplies",
    "Irrigation Direct": "Supplies",

    # Seeds & Fertilizer
    "Nutrien": "Supplies",
    "Helena Chemical": "Supplies",
    "Wilbur-Ellis": "Supplies",

    # ========================================================================
    # CLEANING SUPPLIES & SERVICES
    # ========================================================================

    # Janitorial Supply Stores
    "Uline": "Supplies",
    "Grainger": "Supplies",
    "HD Supply": "Supplies",
    "Imperial Dade": "Supplies",
    "Bunzl": "Supplies",
    "Veritiv": "Supplies",
    "Sysco": "Supplies",
    "US Foods": "Supplies",

    # Retail Cleaning Supplies
    "Walmart": "Supplies",
    "Target": "Supplies",
    "Costco": "Supplies",
    "Sam's Club": "Supplies",
    "BJ's Wholesale Club": "Supplies",
    "Dollar Tree": "Supplies",
    "Dollar General": "Supplies",
    "Family Dollar": "Supplies",

    # Chemical & Cleaning Product Suppliers
    "Ecolab": "Supplies",
    "Cintas": "Supplies",
    "Aramark": "Supplies",
    "Tennant": "Equipment",
    "Nilfisk": "Equipment",

    # Specialty Cleaning
    "Zep": "Supplies",
    "Simple Green": "Supplies",

    # ========================================================================
    # EVENT COORDINATION & RENTALS
    # ========================================================================

    # Party Supply Stores
    "Party City": "Supplies",
    "Oriental Trading": "Supplies",
    "Michaels": "Supplies",
    "Hobby Lobby": "Supplies",
    "Joann": "Supplies",
    "AC Moore": "Supplies",

    # Event Rental Companies
    "Grand Rental Station": "Rent",
    "United Rentals": "Rent",
    "Sunbelt Rentals": "Rent",
    "Hertz Equipment Rental": "Rent",
    "Home Depot Rental": "Rent",
    "Lowe's Tool Rental": "Rent",

    # Table, Chair, Tent Rentals
    "Party Rental": "Rent",
    "Classic Party Rentals": "Rent",
    "Mahaffey": "Rent",
    "CORT Events": "Rent",
    "AFR Furniture Rental": "Rent",

    # Catering & Food Service
    "Sysco": "Meals",
    "US Foods": "Meals",
    "Gordon Food Service": "Meals",
    "Restaurant Depot": "Supplies",
    "Cash & Carry": "Supplies",
    "Chef's Store": "Supplies",
    "Webstaurant Store": "Supplies",

    # Floral & Decorations
    "Flower Wholesale": "Supplies",
    "FiftyFlowers": "Supplies",
    "Blooms by the Box": "Supplies",
    "Accent Decor": "Supplies",

    # Linen & Table Service
    "Linen Tablecloth": "Supplies",
    "Smarty Had a Party": "Supplies",
    "BBJ Linen": "Rent",

    # Audio/Visual
    "Guitar Center": "Equipment",
    "Best Buy": "Equipment",
    "B&H Photo": "Equipment",

    # ========================================================================
    # OFFICE SUPPLIES (Common to All Businesses)
    # ========================================================================

    "Staples": "Office Supplies",
    "Office Depot": "Office Supplies",
    "OfficeMax": "Office Supplies",
    "FedEx Office": "Office Supplies",
    "UPS Store": "Office Supplies",
    "Amazon Business": "Office Supplies",
    "Amazon": "Supplies",

    # ========================================================================
    # MEALS (Common Business Meals)
    # ========================================================================

    # Fast Food
    "Starbucks": "Meals",
    "McDonald's": "Meals",
    "Subway": "Meals",
    "Burger King": "Meals",
    "Wendy's": "Meals",
    "Taco Bell": "Meals",
    "Chick-fil-A": "Meals",
    "Dunkin'": "Meals",
    "Dunkin Donuts": "Meals",
    "Panera": "Meals",
    "Panera Bread": "Meals",
    "Chipotle": "Meals",
    "Five Guys": "Meals",
    "Jimmy John's": "Meals",
    "Jersey Mike's": "Meals",
    "Firehouse Subs": "Meals",
    "Arby's": "Meals",
    "KFC": "Meals",
    "Popeyes": "Meals",
    "Sonic": "Meals",
    "Jack in the Box": "Meals",
    "Carl's Jr": "Meals",
    "Hardee's": "Meals",
    "Whataburger": "Meals",
    "In-N-Out": "Meals",
    "Shake Shack": "Meals",
    "Culver's": "Meals",
    "Raising Cane's": "Meals",
    "Zaxby's": "Meals",
    "Wingstop": "Meals",
    "Buffalo Wild Wings": "Meals",
    "Pizza Hut": "Meals",
    "Domino's": "Meals",
    "Papa John's": "Meals",
    "Little Caesars": "Meals",

    # Coffee
    "Starbucks": "Meals",
    "Dunkin'": "Meals",
    "Tim Hortons": "Meals",
    "Peet's Coffee": "Meals",
    "Caribou Coffee": "Meals",
    "Dutch Bros": "Meals",

    # Casual Dining
    "Applebee's": "Meals",
    "Chili's": "Meals",
    "Olive Garden": "Meals",
    "Red Lobster": "Meals",
    "Outback Steakhouse": "Meals",
    "Texas Roadhouse": "Meals",
    "LongHorn Steakhouse": "Meals",
    "Cracker Barrel": "Meals",
    "IHOP": "Meals",
    "Denny's": "Meals",
    "Waffle House": "Meals",
    "Bob Evans": "Meals",
    "Perkins": "Meals",

    # Delivery Services
    "Uber Eats": "Meals",
    "DoorDash": "Meals",
    "Grubhub": "Meals",
    "Postmates": "Meals",
    "Seamless": "Meals",

    # ========================================================================
    # TRAVEL (Common for Business Travel)
    # ========================================================================

    # Hotels
    "Marriott": "Travel",
    "Hilton": "Travel",
    "Holiday Inn": "Travel",
    "Hampton Inn": "Travel",
    "Hyatt": "Travel",
    "Best Western": "Travel",
    "La Quinta": "Travel",
    "Comfort Inn": "Travel",
    "Quality Inn": "Travel",
    "Motel 6": "Travel",
    "Super 8": "Travel",
    "Days Inn": "Travel",
    "Red Roof Inn": "Travel",
    "Extended Stay": "Travel",
    "Residence Inn": "Travel",
    "Courtyard": "Travel",
    "Fairfield Inn": "Travel",
    "SpringHill Suites": "Travel",
    "Sheraton": "Travel",
    "Westin": "Travel",
    "Doubletree": "Travel",
    "Embassy Suites": "Travel",
    "Homewood Suites": "Travel",
    "Candlewood Suites": "Travel",
    "Staybridge Suites": "Travel",

    # Short-term Rentals
    "Airbnb": "Travel",
    "VRBO": "Travel",
    "HomeAway": "Travel",

    # Airlines
    "American Airlines": "Travel",
    "Delta": "Travel",
    "United": "Travel",
    "Southwest": "Travel",
    "JetBlue": "Travel",
    "Alaska Airlines": "Travel",
    "Spirit": "Travel",
    "Frontier": "Travel",
    "Allegiant": "Travel",

    # Rideshare & Transportation
    "Uber": "Travel",
    "Lyft": "Travel",
    "Via": "Travel",

    # Rental Cars
    "Enterprise": "Travel",
    "Hertz": "Travel",
    "Budget": "Travel",
    "Avis": "Travel",
    "National": "Travel",
    "Alamo": "Travel",
    "Dollar": "Travel",
    "Thrifty": "Travel",
    "Sixt": "Travel",
    "Zipcar": "Travel",
    "Turo": "Travel",

    # Tolls & Parking
    "ParkWhiz": "Travel",
    "SpotHero": "Travel",
    "Park Mobile": "Travel",
    "E-ZPass": "Travel",
    "SunPass": "Travel",

    # ========================================================================
    # INSURANCE
    # ========================================================================

    "State Farm": "Insurance",
    "Geico": "Insurance",
    "Progressive": "Insurance",
    "Allstate": "Insurance",
    "Farmers": "Insurance",
    "USAA": "Insurance",
    "Liberty Mutual": "Insurance",
    "Nationwide": "Insurance",
    "Travelers": "Insurance",
    "American Family": "Insurance",
    "Erie": "Insurance",
    "Auto-Owners": "Insurance",
    "The Hartford": "Insurance",
    "Safeco": "Insurance",
    "Mercury": "Insurance",

    # ========================================================================
    # UTILITIES
    # ========================================================================

    # Common Utility Keywords (customize based on your region)
    "Electric Company": "Utilities",
    "Power Company": "Utilities",
    "Water Department": "Utilities",
    "Gas Company": "Utilities",
    "Internet Provider": "Utilities",
    "Phone Service": "Utilities",

    # Telecom
    "Verizon": "Utilities",
    "AT&T": "Utilities",
    "T-Mobile": "Utilities",
    "Sprint": "Utilities",
    "Comcast": "Utilities",
    "Xfinity": "Utilities",
    "Spectrum": "Utilities",
    "Cox": "Utilities",
    "Optimum": "Utilities",
    "Frontier": "Utilities",
    "CenturyLink": "Utilities",

    # ========================================================================
    # BANK FEES
    # ========================================================================

    "Bank Fee": "Bank Fees",
    "Service Charge": "Bank Fees",
    "Overdraft Fee": "Bank Fees",
    "Wire Fee": "Bank Fees",
    "ATM Fee": "Bank Fees",
    "Monthly Fee": "Bank Fees",
    "Maintenance Fee": "Bank Fees",

    # ========================================================================
    # ADVERTISING & MARKETING
    # ========================================================================

    "Google Ads": "Advertising & Marketing",
    "Facebook Ads": "Advertising & Marketing",
    "Meta Ads": "Advertising & Marketing",
    "Instagram Ads": "Advertising & Marketing",
    "LinkedIn Ads": "Advertising & Marketing",
    "Twitter Ads": "Advertising & Marketing",
    "X Ads": "Advertising & Marketing",
    "Yelp": "Advertising & Marketing",
    "Yelp Ads": "Advertising & Marketing",
    "Angie's List": "Advertising & Marketing",
    "Angi": "Advertising & Marketing",
    "HomeAdvisor": "Advertising & Marketing",
    "Thumbtack": "Advertising & Marketing",
    "Porch": "Advertising & Marketing",
    "Bark": "Advertising & Marketing",
    "Nextdoor": "Advertising & Marketing",
    "Nextdoor Ads": "Advertising & Marketing",
    "Constant Contact": "Advertising & Marketing",
    "Mailchimp": "Advertising & Marketing",
    "HubSpot": "Advertising & Marketing",
    "ActiveCampaign": "Advertising & Marketing",
    "SendGrid": "Advertising & Marketing",
    "Vistaprint": "Advertising & Marketing",
    "Moo": "Advertising & Marketing",
    "GotPrint": "Advertising & Marketing",
    "PrintRunner": "Advertising & Marketing",

    # ========================================================================
    # SOFTWARE & SUBSCRIPTIONS
    # ========================================================================

    "QuickBooks": "Software & Subscriptions",
    "Quickbooks Online": "Software & Subscriptions",
    "Xero": "Software & Subscriptions",
    "FreshBooks": "Software & Subscriptions",
    "Wave": "Software & Subscriptions",
    "Gusto": "Software & Subscriptions",
    "ADP": "Software & Subscriptions",
    "Paychex": "Software & Subscriptions",
    "Square": "Software & Subscriptions",
    "Stripe": "Software & Subscriptions",
    "PayPal": "Software & Subscriptions",
    "Venmo": "Software & Subscriptions",
    "Zoom": "Software & Subscriptions",
    "Microsoft 365": "Software & Subscriptions",
    "Office 365": "Software & Subscriptions",
    "Google Workspace": "Software & Subscriptions",
    "G Suite": "Software & Subscriptions",
    "Dropbox": "Software & Subscriptions",
    "Adobe": "Software & Subscriptions",
    "Adobe Creative Cloud": "Software & Subscriptions",
    "Canva": "Software & Subscriptions",
    "Slack": "Software & Subscriptions",
    "Asana": "Software & Subscriptions",
    "Monday.com": "Software & Subscriptions",
    "Trello": "Software & Subscriptions",
    "ClickUp": "Software & Subscriptions",
    "Notion": "Software & Subscriptions",
    "Salesforce": "Software & Subscriptions",
    "Shopify": "Software & Subscriptions",
    "Wix": "Software & Subscriptions",
    "Squarespace": "Software & Subscriptions",
    "GoDaddy": "Software & Subscriptions",
    "Bluehost": "Software & Subscriptions",
    "HostGator": "Software & Subscriptions",
    "AWS": "Software & Subscriptions",
    "Amazon Web Services": "Software & Subscriptions",
    "Azure": "Software & Subscriptions",
    "Google Cloud": "Software & Subscriptions",
    "Heroku": "Software & Subscriptions",
    "DigitalOcean": "Software & Subscriptions",
    "Netlify": "Software & Subscriptions",
    "Vercel": "Software & Subscriptions",

    # ========================================================================
    # EQUIPMENT (Heavy Equipment Rental)
    # ========================================================================

    "United Rentals": "Equipment",
    "Sunbelt Rentals": "Equipment",
    "Herc Rentals": "Equipment",
    "BigRentz": "Equipment",
    "Cat Rental": "Equipment",
    "Caterpillar Rental": "Equipment",
    "Home Depot Tool Rental": "Equipment",
    "Lowe's Tool Rental": "Equipment",

    # ========================================================================
    # CONTRACT LABOR & STAFFING
    # ========================================================================

    "Indeed": "Contract Labor",
    "ZipRecruiter": "Contract Labor",
    "LinkedIn": "Contract Labor",
    "Monster": "Contract Labor",
    "CareerBuilder": "Contract Labor",
    "Upwork": "Contract Labor",
    "Fiverr": "Contract Labor",
    "Freelancer": "Contract Labor",
    "TaskRabbit": "Contract Labor",
    "Wonolo": "Contract Labor",
    "Manpower": "Contract Labor",
    "Kelly Services": "Contract Labor",
    "Robert Half": "Contract Labor",
    "Randstad": "Contract Labor",
    "Adecco": "Contract Labor",
}

# ============================================================================
# KEYWORD CATEGORY MAP
# Used when vendor is unknown or generic
# ============================================================================

KEYWORD_CATEGORY_MAP: Dict[str, str] = {
    # Fuel keywords
    "fuel": "Fuel",
    "gas": "Fuel",
    "gasoline": "Fuel",
    "diesel": "Fuel",
    "pump": "Fuel",

    # Car & Truck keywords
    "autozone": "Car & Truck",
    "auto zone": "Car & Truck",
    "advance auto": "Car & Truck",
    "o'reilly": "Car & Truck",
    "oreilly": "Car & Truck",
    "tires": "Car & Truck",
    "tire": "Car & Truck",
    "oil change": "Car & Truck",
    "brake": "Car & Truck",
    "battery": "Car & Truck",
    "wiper": "Car & Truck",
    "alignment": "Car & Truck",

    # Office Supplies keywords
    "office": "Office Supplies",
    "staples": "Office Supplies",
    "paper": "Office Supplies",
    "printer": "Office Supplies",
    "ink": "Office Supplies",
    "toner": "Office Supplies",
    "notebook": "Office Supplies",
    "pens": "Office Supplies",
    "post-it": "Office Supplies",

    # Software & Subscriptions keywords
    "subscription": "Software & Subscriptions",
    "saas": "Software & Subscriptions",
    "software": "Software & Subscriptions",
    "monthly": "Software & Subscriptions",
    "annual": "Software & Subscriptions",
    "stripe": "Software & Subscriptions",
    "quickbooks": "Software & Subscriptions",
    "adobe": "Software & Subscriptions",
    "microsoft 365": "Software & Subscriptions",
    "google workspace": "Software & Subscriptions",
    "aws": "Software & Subscriptions",
    "azure": "Software & Subscriptions",
    "gcp": "Software & Subscriptions",
    "dropbox": "Software & Subscriptions",
    "notion": "Software & Subscriptions",

    # Supplies keywords
    "supplies": "Supplies",
    "supply": "Supplies",
    "inventory": "Supplies",
    "restock": "Supplies",
    "materials": "Supplies",

    # Repairs & Maintenance keywords
    "repair": "Repairs & Maintenance",
    "maintenance": "Repairs & Maintenance",
    "service": "Repairs & Maintenance",
    "labor": "Repairs & Maintenance",
    "parts": "Repairs & Maintenance",
    "fix": "Repairs & Maintenance",
    "replace": "Repairs & Maintenance",

    # Equipment keywords
    "equipment": "Equipment",
    "tool": "Equipment",
    "tools": "Equipment",
    "machine": "Equipment",
    "hardware": "Equipment",
    "laptop": "Equipment",
    "computer": "Equipment",
    "monitor": "Equipment",
    "router": "Equipment",

    # Advertising & Marketing keywords
    "marketing": "Advertising & Marketing",
    "advertising": "Advertising & Marketing",
    "ads": "Advertising & Marketing",
    "facebook ads": "Advertising & Marketing",
    "google ads": "Advertising & Marketing",
    "promotion": "Advertising & Marketing",
    "sponsor": "Advertising & Marketing",

    # Meals keywords
    "restaurant": "Meals",
    "meal": "Meals",
    "lunch": "Meals",
    "dinner": "Meals",
    "breakfast": "Meals",
    "cafe": "Meals",
    "coffee": "Meals",
    "starbucks": "Meals",
    "mcdonald": "Meals",
    "subway": "Meals",
    "doordash": "Meals",
    "uber eats": "Meals",

    # Travel keywords
    "hotel": "Travel",
    "airbnb": "Travel",
    "flight": "Travel",
    "airline": "Travel",
    "uber": "Travel",
    "lyft": "Travel",
    "taxi": "Travel",
    "rental car": "Travel",
    "parking": "Travel",
    "toll": "Travel",

    # Utilities keywords
    "electric": "Utilities",
    "water": "Utilities",
    "internet": "Utilities",
    "wifi": "Utilities",
    "utility": "Utilities",
    "phone bill": "Utilities",
    "verizon": "Utilities",
    "at&t": "Utilities",
    "t-mobile": "Utilities",

    # Insurance keywords
    "insurance": "Insurance",
    "premium": "Insurance",
    "policy": "Insurance",

    # Rent keywords
    "rent": "Rent",
    "lease": "Rent",

    # Bank Fees keywords
    "fee": "Bank Fees",
    "service charge": "Bank Fees",
    "overdraft": "Bank Fees",
    "wire fee": "Bank Fees",
    "atm fee": "Bank Fees",
}


# ============================================================================
# BUSINESS TYPE DEFAULTS
# Default category fallback based on business type
# ============================================================================

BUSINESS_TYPE_DEFAULTS: Dict[str, str] = {
    # Real Estate
    "realtor": "Advertising & Marketing",
    "real estate agent": "Advertising & Marketing",

    # Construction & Trades
    "contractor": "Supplies",
    "general contractor": "Supplies",
    "electrician": "Supplies",
    "plumber": "Supplies",
    "hvac": "Supplies",
    "carpenter": "Supplies",
    "roofer": "Supplies",
    "painter": "Supplies",

    # Auto Services
    "mechanic": "Car & Truck",
    "auto repair": "Car & Truck",
    "auto mechanic": "Car & Truck",
    "mobile mechanic": "Car & Truck",

    # Cleaning Services
    "cleaner": "Supplies",
    "cleaning service": "Supplies",
    "janitorial": "Supplies",
    "maid service": "Supplies",
    "house cleaner": "Supplies",
    "commercial cleaner": "Supplies",

    # Landscaping & Lawn Care
    "landscaper": "Supplies",
    "lawn care": "Supplies",
    "groundskeeper": "Supplies",
    "tree service": "Supplies",
    "gardener": "Supplies",
    "landscape maintenance": "Supplies",

    # Event Services
    "event coordinator": "Supplies",
    "event planner": "Supplies",
    "wedding planner": "Supplies",
    "party planner": "Supplies",

    # Professional Services
    "consultant": "Software & Subscriptions",
    "freelancer": "Software & Subscriptions",
    "developer": "Software & Subscriptions",
    "designer": "Software & Subscriptions",
    "photographer": "Equipment",
    "videographer": "Equipment",

    # Food Services
    "food": "Supplies",
    "restaurant": "Supplies",
    "catering": "Supplies",
    "food truck": "Supplies",
    "bakery": "Supplies",
    "cafe": "Supplies",
}


# ============================================================================
# BUSINESS TYPE HINTS
# Used by engine.py to boost certain categories for specific business types
# ============================================================================

BUSINESS_TYPE_HINTS: Dict[str, Dict[str, List[str]]] = {
    # Real Estate
    "realtor": {
        "Advertising & Marketing": ["listing", "mls", "open house", "staging", "sign", "flyer", "zillow", "realtor.com"],
        "Travel": ["showing", "client meeting", "site visit"],
        "Office Supplies": ["lockbox", "signs", "brochure"],
    },

    # Construction & Contractors
    "contractor": {
        "Supplies": ["lumber", "drywall", "concrete", "paint", "tile", "hardware", "plywood", "screws", "nails"],
        "Equipment": ["drill", "saw", "compressor", "ladder", "scaffolding"],
        "Contract Labor": ["subcontractor", "helper", "labor"],
    },

    # Auto Mechanics
    "mechanic": {
        "Car & Truck": ["parts", "oil", "filter", "brake pad", "rotor", "spark plug", "battery", "alternator", "starter"],
        "Equipment": ["diagnostic", "lift", "scanner", "tools"],
        "Supplies": ["shop towels", "degreaser", "cleaner"],
    },

    # Cleaning Services
    "cleaner": {
        "Supplies": ["cleaning supplies", "bleach", "disinfectant", "mop", "vacuum bags", "trash bags", "paper towels", "gloves"],
        "Equipment": ["vacuum", "carpet cleaner", "buffer", "steamer"],
        "Contract Labor": ["crew", "helper", "staff"],
    },

    # Landscapers
    "landscaper": {
        "Supplies": ["mulch", "soil", "plants", "seed", "fertilizer", "stone", "gravel", "edging", "weed killer"],
        "Equipment": ["mower", "trimmer", "blower", "chainsaw", "edger", "aerator"],
        "Fuel": ["gas", "fuel", "oil mix"],
        "Repairs & Maintenance": ["blade sharpening", "equipment repair", "mower service"],
    },

    # Event Coordinators
    "event coordinator": {
        "Supplies": ["decorations", "tablecloths", "centerpieces", "balloons", "flowers", "party supplies"],
        "Rent": ["tent", "tables", "chairs", "linens", "venue"],
        "Meals": ["catering", "food", "beverages"],
        "Contract Labor": ["staff", "servers", "bartender", "dj", "photographer"],
    },

    # Food Services
    "food": {
        "Supplies": ["ingredients", "produce", "meat", "dairy", "packaging", "containers", "utensils"],
        "Equipment": ["oven", "mixer", "fridge", "freezer", "cookware"],
        "Repairs & Maintenance": ["appliance repair", "equipment service"],
    },

    # Photographers
    "photographer": {
        "Equipment": ["camera", "lens", "lighting", "tripod", "memory card", "battery"],
        "Software & Subscriptions": ["adobe", "lightroom", "photoshop", "smugmug"],
        "Travel": ["shoot", "session", "location"],
    },

    # Electricians
    "electrician": {
        "Supplies": ["wire", "conduit", "breaker", "outlet", "switch", "junction box", "cable"],
        "Equipment": ["multimeter", "wire stripper", "fish tape", "tools"],
        "Contract Labor": ["apprentice", "helper"],
    },

    # Plumbers
    "plumber": {
        "Supplies": ["pipe", "fitting", "valve", "toilet", "sink", "faucet", "drain cleaner"],
        "Equipment": ["snake", "camera", "torch", "wrench"],
        "Contract Labor": ["apprentice", "helper"],
    },

    # HVAC
    "hvac": {
        "Supplies": ["refrigerant", "filter", "thermostat", "ductwork", "insulation"],
        "Equipment": ["gauges", "vacuum pump", "recovery machine", "torch"],
        "Contract Labor": ["apprentice", "installer"],
    },
}

