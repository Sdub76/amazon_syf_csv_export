import re
import csv
import sys
import argparse
from PyPDF2 import PdfReader
import os
from datetime import datetime, timedelta

def extract_text_from_pdf(pdf_path):
    """Extract all text from a PDF file, with page breaks preserved."""
    reader = PdfReader(pdf_path)
    pages_text = []
    for page in reader.pages:
        pages_text.append(page.extract_text())
    return pages_text

def clean_description(description):
    """Clean the description by removing random strings and any AMAZON [...] WA patterns."""
    # Remove 12-character alphanumeric strings (likely order IDs)
    description = re.sub(r'\b[A-Za-z0-9]{12}\b', '', description)
    
    # Remove any "AMAZON [...] WA" patterns (more general pattern)
    description = re.sub(r'AMAZON.*?WA', '', description)
    
    # Clean up extra spaces
    description = re.sub(r'\s+', ' ', description).strip()
    
    return description

def extract_date_range(text):
    """Extract billing cycle date range from the PDF text."""
    # Try the standard billing cycle pattern
    match = re.search(r'Billing Cycle from (\d{2}/\d{2}/\d{4}) to (\d{2}/\d{2}/\d{4})', text)
    if match:
        start_date = match.group(1)
        end_date = match.group(2)
        return start_date, end_date
    
    # Try an alternative pattern if the standard one isn't found
    alt_match = re.search(r'(\d{2}/\d{2}/\d{4}) to (\d{2}/\d{2}/\d{4})', text)
    if alt_match:
        start_date = alt_match.group(1)
        end_date = alt_match.group(2)
        return start_date, end_date
        
    return None, None

def extract_statement_date(text):
    """Extract the statement date from the PDF text if possible."""
    match = re.search(r'New Balance as of (\d{2}/\d{2}/\d{4})', text)
    if match:
        return match.group(1)
    return None

def extract_account_balance_summary(text):
    """Extract account balance summary data to use for verification."""
    account_summary = {}
    
    # Try to find the Account Summary section first (at the top of the statement)
    # This pattern better matches the format in the provided statement
    summary_match = re.search(r'Account Summary.*?Payments\s+-\s+([\d,]+\.\d{2}).*?Other Credits\s+-\s+([\d,]+\.\d{2}).*?Purchases/Debits\s+\+\s+([\d,]+\.\d{2})', text, re.DOTALL)
    if summary_match:
        payments = summary_match.group(1)
        other_credits = summary_match.group(2)
        purchases = summary_match.group(3)
        
        # Calculate total payments and credits
        total_payments_credits = float(payments.replace(',', '')) + float(other_credits.replace(',', ''))
        account_summary['payments_other_credits'] = round(total_payments_credits, 2)
        account_summary['purchases_debits'] = float(purchases.replace(',', ''))
        return account_summary
    
    # Try to find payments and credits in the Account Balance Summary section
    account_balance_match = re.search(r'Account Balance Summary(.*?)Transaction Detail', text, re.DOTALL)
    if not account_balance_match:
        # Try another pattern for finding the section
        account_balance_match = re.search(r'Account Balance Summary(.*?)Total Fees Charged This Period', text, re.DOTALL)
        if not account_balance_match:
            return None
    
    account_balance_section = account_balance_match.group(1)
    
    # Look for the tabular format in Account Balance Summary
    # This pattern captures the values in the "Payments & Other Credits" column
    credits_match = re.search(r'Regular.*?\$([\d,]+\.\d{2})', account_balance_section)
    if credits_match:
        account_summary['payments_other_credits'] = float(credits_match.group(1).replace(',', ''))
        
        # Look for the purchases & debits value
        purchases_match = re.search(r'Regular.*?\$[\d,]+\.\d{2}\s+\$([\d,]+\.\d{2})', account_balance_section)
        if purchases_match:
            account_summary['purchases_debits'] = float(purchases_match.group(1).replace(',', ''))
        return account_summary
    
    # Try alternative patterns for finding payment and purchase values
    payments_match = re.search(r'Payments & Other Credits\s+\(-\)\s+\$([\d,]+\.\d{2})', account_balance_section)
    if payments_match:
        account_summary['payments_other_credits'] = float(payments_match.group(1).replace(',', ''))
    
    purchases_match = re.search(r'Purchases, Fees & Others Debits\s+\(\+\)\s+\$([\d,]+\.\d{2})', account_balance_section)
    if purchases_match:
        account_summary['purchases_debits'] = float(purchases_match.group(1).replace(',', ''))
    
    return account_summary

def extract_transactions(pages_text, pdf_filename=None):
    """Extract transactions from statement text across multiple pages."""
    # Extract date information from the first page
    start_date, end_date = extract_date_range(pages_text[0]) if pages_text else (None, None)
    statement_date = extract_statement_date(pages_text[0]) if pages_text else None
    
    # Debug output
    if start_date and end_date:
        print(f"  Found billing cycle: {start_date} to {end_date}")
    elif statement_date:
        print(f"  Found statement date: {statement_date}")
    
    # Extract account balance summary for verification
    combined_text = "\n".join(pages_text)
    account_summary = extract_account_balance_summary(combined_text)
    
    # Find the transaction section
    all_transactions = []
    current_transaction = None
    in_transaction_section = False
    column_headers_pattern = r"Date\s+Reference #\s+Description\s+Amount"
    
    # Combine all pages into a single text while preserving page separations
    for page_idx, page_text in enumerate(pages_text):
        # Skip processing if we're not in transaction section yet
        if not in_transaction_section:
            start_match = re.search(r"Transaction Detail", page_text)
            if start_match:
                in_transaction_section = True
                # Get text after "Transaction Detail"
                page_text = page_text[start_match.end():]
            else:
                continue
        
        # Check if transaction section ends on this page
        end_match = re.search(r"Total Fees Charged This Period", page_text)
        if end_match:
            # Only process up to this point
            page_text = page_text[:end_match.start()]
            in_transaction_section = False
        
        # Check for "continued on next page" and ignore the rest of this page if found
        continued_match = re.search(r"continued on next page", page_text, re.IGNORECASE)
        if continued_match:
            page_text = page_text[:continued_match.start()]
        
        # For pages after the first page in transaction section, 
        # skip text until after column headers
        if page_idx > 0:
            headers_match = re.search(column_headers_pattern, page_text)
            if headers_match:
                page_text = page_text[headers_match.end():]
        
        # Process the lines on this page
        lines = page_text.strip().split('\n')
        for line in lines:
            if not line.strip():
                continue
                
            # Look for the section headers in the transaction details
            if re.search(r"^Payments -\$[\d,]+\.\d{2}$", line) or re.search(r"^Other Credits -\$[\d,]+\.\d{2}$", line) or re.search(r"^Purchases and Other Debits \$[\d,]+\.\d{2}$", line):
                continue
                
            # Special case for statement credits (no reference number)
            statement_credit_match = re.search(r"(\d{2}/\d{2})\s+YOUR STORE CARD STATEMENT CREDIT\s+-\$([\d,]+\.\d{2})", line)
            if statement_credit_match:
                date, amount = statement_credit_match.groups()
                # Add year based on billing cycle
                date_with_year = add_year_to_date(date, start_date, end_date, statement_date)
                
                # For payments/credits, amount should be positive
                amount_value = amount.replace(',', '')
                
                all_transactions.append({
                    'date': date_with_year,
                    'reference': '',  # Empty reference
                    'description': 'YOUR STORE CARD STATEMENT CREDIT',
                    'amount': amount_value,  # Already positive
                    'source': pdf_filename if pdf_filename else 'Unknown'
                })
                current_transaction = None
                continue
                
            # Check if this is a payment entry (starting with a minus sign)
            payment_match = re.search(r"(\d{2}/\d{2})\s+([A-Z0-9]+)?\s+(.*?)\s+-\$([\d,]+\.\d{2})", line)
            if payment_match:
                date, ref, desc, amount = payment_match.groups()
                # Add year based on billing cycle
                date_with_year = add_year_to_date(date, start_date, end_date, statement_date)
                
                # For payments/credits, amount should be positive
                amount_value = amount.replace(',', '')
                
                all_transactions.append({
                    'date': date_with_year,
                    'reference': ref if ref else '',
                    'description': clean_description(desc.strip()),
                    'amount': amount_value,  # Already positive
                    'source': pdf_filename if pdf_filename else 'Unknown'
                })
                current_transaction = None
                continue
                
            # Check if this is a new transaction (purchase)
            transaction_match = re.search(r"(\d{2}/\d{2})\s+([A-Z0-9]+)?\s+(.*?)\s+\$([\d,]+\.\d{2})", line)
            if transaction_match:
                date, ref, desc, amount = transaction_match.groups()
                # Add year based on billing cycle
                date_with_year = add_year_to_date(date, start_date, end_date, statement_date)
                
                # For purchases, invert the sign (make it negative)
                amount_value = f"-{amount.replace(',', '')}"
                
                current_transaction = {
                    'date': date_with_year,
                    'reference': ref if ref else '',
                    'description': desc.strip(),  # Store raw description initially
                    'amount': amount_value,
                    'source': pdf_filename if pdf_filename else 'Unknown'
                }
                all_transactions.append(current_transaction)
            elif current_transaction and line.strip():
                # This is a continuation of a description from the previous transaction
                current_transaction['description'] += ' ' + line.strip()
        
        # If we reached the end of the transaction section, break
        if not in_transaction_section:
            break
    
    # Clean all descriptions after they're fully assembled
    for transaction in all_transactions:
        transaction['description'] = clean_description(transaction['description'])
    
    if all_transactions:
        print(f"  Found {len(all_transactions)} transactions in {pdf_filename if pdf_filename else 'statement'}")
    else:
        print(f"  No transactions found in {pdf_filename if pdf_filename else 'statement'}")

    # Return transactions and account summary for verification
    return all_transactions, account_summary

def parse_date(date_str):
    """Parse a date string in MM/DD/YYYY format and return a datetime object."""
    if not date_str:
        return None
    try:
        if len(date_str) == 10:  # MM/DD/YYYY
            month, day, year = date_str.split('/')
            return datetime(int(year), int(month), int(day))
    except (ValueError, TypeError):
        pass
    return None

def add_year_to_date(date_str, start_date, end_date, statement_date=None):
    """
    Add year to MM/DD format dates based on billing cycle date range.
    
    Logic:
    1. If date is within the billing cycle, use the appropriate year
    2. If date is outside the billing cycle, assume it's from before the start date
    3. Never assume a date is after the end date of the statement
    """
    if not date_str or len(date_str) != 5:  # Expecting MM/DD format
        return date_str
    
    transaction_month, transaction_day = map(int, date_str.split('/'))
    
    # Parse billing cycle dates
    start_date_obj = parse_date(start_date)
    end_date_obj = parse_date(end_date)
    
    # If we have valid billing cycle dates
    if start_date_obj and end_date_obj:
        start_year = start_date_obj.year
        end_year = end_date_obj.year
        start_month = start_date_obj.month
        start_day = start_date_obj.day
        end_month = end_date_obj.month
        end_day = end_date_obj.day
        
        # Check if date is within billing cycle
        is_after_start = (transaction_month > start_month or 
                         (transaction_month == start_month and transaction_day >= start_day))
        is_before_end = (transaction_month < end_month or 
                        (transaction_month == end_month and transaction_day <= end_day))
        
        # Handle year transition (Dec to Jan)
        if end_month < start_month:  # Cycle crosses a year boundary
            if transaction_month >= start_month or transaction_month <= end_month:
                # Date is within cycle, determine appropriate year
                if transaction_month >= start_month:
                    return f"{date_str}/{start_year}"
                else:  # transaction_month <= end_month
                    return f"{date_str}/{end_year}"
            else:
                # Date is outside of cycle, assume it's from before start date
                return f"{date_str}/{start_year}"
        else:  # Normal cycle within same year
            if is_after_start and is_before_end:
                return f"{date_str}/{start_year}"
            else:
                # Date is outside of cycle, assume it's from before start date
                # Typically the previous month but same year as start_date
                return f"{date_str}/{start_year}"
    
    # Fallback to statement date logic
    if statement_date:
        statement_date_obj = parse_date(statement_date)
        if statement_date_obj:
            statement_year = statement_date_obj.year
            # If statement month is early in year and transaction is late in year, 
            # transaction likely from previous year
            if statement_date_obj.month <= 3 and transaction_month >= 10:
                return f"{date_str}/{statement_year-1}"
            else:
                return f"{date_str}/{statement_year}"
    
    # Last resort: current year
    current_year = datetime.now().year
    return f"{date_str}/{current_year}"

def verify_transactions(transactions, account_summary, pdf_filename):
    """
    Verify that the transaction totals match the account summary values.
    Returns True if verification passed, False otherwise.
    """
    if not account_summary:
        print(f"  WARNING: Could not extract account summary for verification in {pdf_filename}")
        return False
    
    # Calculate totals from transactions
    negative_transactions = [float(t['amount']) for t in transactions if float(t['amount']) > 0]
    positive_transactions = [abs(float(t['amount'])) for t in transactions if float(t['amount']) < 0]
    
    total_negative = round(sum(negative_transactions), 2)
    total_positive = round(sum(positive_transactions), 2)
    
    print("\n=== Transaction Verification ===")
    print(f"File: {pdf_filename}")
    
    verification_passed = True
    
    # Verify negative transactions (payments and credits)
    if 'payments_other_credits' in account_summary:
        expected_negative = account_summary['payments_other_credits']
        print(f"  Payments & Other Credits:")
        print(f"    Expected: ${expected_negative:.2f}")
        print(f"    Actual: ${total_negative:.2f}")
        
        if abs(total_negative - expected_negative) < 0.02:  # Allow for small rounding errors
            print(f"    ✅ MATCH")
        else:
            print(f"    ❌ MISMATCH (Difference: ${abs(total_negative - expected_negative):.2f})")
            verification_passed = False
    else:
        print(f"  ⚠️ Could not find expected value for 'Payments & Other Credits'")
    
    # Verify positive transactions (purchases and debits)
    if 'purchases_debits' in account_summary:
        expected_positive = account_summary['purchases_debits']
        print(f"  Purchases, Fees & Other Debits:")
        print(f"    Expected: ${expected_positive:.2f}")
        print(f"    Actual: ${total_positive:.2f}")
        
        if abs(total_positive - expected_positive) < 0.02:  # Allow for small rounding errors
            print(f"    ✅ MATCH")
        else:
            print(f"    ❌ MISMATCH (Difference: ${abs(total_positive - expected_positive):.2f})")
            verification_passed = False
    else:
        print(f"  ⚠️ Could not find expected value for 'Purchases, Fees & Other Debits'")
    
    # Overall verification status
    if verification_passed:
        print(f"\n✅ VERIFICATION PASSED for {pdf_filename}\n")
    else:
        print(f"\n❌ VERIFICATION FAILED for {pdf_filename}\n")
    
    return verification_passed

def process_pdf_file(pdf_path):
    """Process a single PDF file and return its transactions."""
    try:
        print(f"Processing {pdf_path}...")
        pages_text = extract_text_from_pdf(pdf_path)
        transactions, account_summary = extract_transactions(pages_text, os.path.basename(pdf_path))
        
        # Verify transaction totals
        verification_passed = verify_transactions(transactions, account_summary, os.path.basename(pdf_path))
        
        return transactions, verification_passed
    except Exception as e:
        print(f"  Error processing {pdf_path}: {e}")
        return [], False

def write_to_csv(transactions, output_path):
    """Write transactions to a CSV file."""
    if not transactions:
        print("No transactions to write")
        return
    
    with open(output_path, 'w', newline='') as csvfile:
        fieldnames = ['date', 'reference', 'description', 'amount', 'source']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        
        # Improved date sorting - convert string dates to datetime objects for proper sorting
        def get_transaction_date(transaction):
            date_str = transaction['date']
            try:
                if date_str and len(date_str) == 10:  # MM/DD/YYYY format
                    month, day, year = date_str.split('/')
                    return datetime(int(year), int(month), int(day))
                return datetime(1900, 1, 1)  # Default for invalid dates
            except (ValueError, TypeError):
                return datetime(1900, 1, 1)  # Return a default date for invalid formats
        
        # Sort transactions by date
        sorted_transactions = sorted(transactions, key=get_transaction_date)
        
        for transaction in sorted_transactions:
            writer.writerow(transaction)
    
    print(f"CSV file created successfully: {output_path}")
    print(f"Total transactions written: {len(transactions)}")

def main():
    parser = argparse.ArgumentParser(description='Extract transactions from Amazon credit card statements.')
    parser.add_argument('pdf_files', nargs='+', help='PDF statement files to process')
    parser.add_argument('-o', '--output', default='amazon_transactions.csv', 
                      help='Output CSV file name (default: amazon_transactions.csv)')
    
    args = parser.parse_args()
    
    all_transactions = []
    verification_results = []
    
    # Process each PDF file
    for pdf_path in args.pdf_files:
        if os.path.exists(pdf_path):
            transactions, verification_passed = process_pdf_file(pdf_path)
            all_transactions.extend(transactions)
            verification_results.append((os.path.basename(pdf_path), verification_passed))
        else:
            print(f"File not found: {pdf_path}")
            verification_results.append((os.path.basename(pdf_path), False))
    
    # Write all transactions to a single CSV file
    write_to_csv(all_transactions, args.output)
    
    # Print summary of verification results
    print("\n=== Verification Summary ===")
    all_passed = True
    for filename, passed in verification_results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{filename}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n✅ ALL FILES PASSED VERIFICATION")
    else:
        print("\n⚠️ SOME FILES FAILED VERIFICATION - Please check the results above")

if __name__ == "__main__":
    main()
