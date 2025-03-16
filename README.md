# Amazon Credit Card Statement Transaction Extractor

A Python utility for CSV extraction of transaction data from Amazon credit card (Sychrony) statement PDFs.

## Features

- **Data Extraction:** Automatically extracts transaction details from statement PDFs
- **Data Verification:** Verifies the extracted transactions against statement summary totals
- **Transaction Sorting:** Chronologically sorts all transactions across multiple statements
- **Date Handling:** Intelligently adds year information to transaction dates
- **Multi-file Support:** Process multiple PDF files in a single run

## Requirements

- Python 3.6+
- PyPDF2 library
- Standard libraries: re, csv, os, datetime, argparse

## Installation

1. Clone this repository or download the script file:

```bash
git clone https://github.com/sdub76/amazon_syf_csv_export.git
cd amazon_syf_csv_export
```

2. Set up a virtual environment (recommended):

```bash
# Create a virtual environment
python3 -m venv amazon_syf_csv_export --system-site-packages
```
```bash
# Activate the virtual environment
# On Windows:
amazon_syf_csv_export\Scripts\activate
```
```bash
# On macOS/Linux/WSL:
source amazon_syf_csv_export/bin/activate
```

3. Install required dependencies:

```bash
pip install PyPDF2
```

4. When you're done using the program, you can deactivate the virtual environment:

```bash
deactivate
```

## Usage

### Basic Usage

Process one or more PDF statement files:

```bash
python amazon_parse.py statement1.pdf statement2.pdf
```

This will:
- Process each PDF file
- Extract and verify all transactions
- Create a CSV file (`amazon_transactions.csv` by default) with all transactions sorted by date

### Advanced Options

Specify a custom output file name:

```bash
python amazon_parse.py statement1.pdf statement2.pdf -o my_transactions.csv
```

### Output

The script generates:

1. A CSV file with the following columns:
   - `date`: Transaction date in MM/DD/YYYY format
   - `reference`: Reference number for the transaction (if available)
   - `description`: Cleaned transaction description
   - `amount`: Transaction amount (positive for payments/credits, negative for purchases)
   - `source`: Source statement file

2. Console output showing:
   - Processing status for each file
   - Verification results comparing transaction totals against statement totals
   - Summary of verification results for all files

## How It Works

1. **PDF Parsing:**
   - Extracts text from PDF statements using PyPDF2
   - Handles multi-page statements and preserves page structure

2. **Data Extraction:**
   - Finds transaction section using regex patterns
   - Extracts billing cycle dates and statement dates
   - Parses individual transactions with date, reference number, description, and amount
   - Cleans up transaction descriptions by removing order IDs and location information

3. **Verification:**
   - Extracts account summary information from the statement
   - Compares total payments/credits and purchases/debits against expected values
   - Reports any mismatches with detailed difference information

4. **Date Handling:**
   - Adds missing year information to transaction dates based on billing cycle
   - Handles year transitions (December to January) correctly

5. **Output Generation:**
   - Sorts all transactions chronologically by date
   - Writes results to a CSV file

## Troubleshooting

- **PDF Compatibility:** The script is designed to work with Amazon credit card statement PDFs. Different statement formats may require adjustments to the regex patterns.
- **Verification Failures:** If verification fails, check if the statement has any unusual formatting or if there are transactions that span across multiple pages.
- **Year Assignment:** The script attempts to determine the correct year for each transaction. If you notice incorrect years, check the billing cycle dates in your statements.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
