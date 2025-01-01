import PyPDF2
import pdfplumber
import pandas as pd
import re

# Define mappings for inconsistent headings
COLUMN_MAPPINGS = {
    "description": ["Description", "Transaction Details", "Remark", "Details", "details"],
    "amount": ["Amount", "Transaction Amount", "Debit/Credit", "Value", "amount"],
    "date": ["Date", "Transaction Date", "Posting Date", "date"],
}

def read_pdf(file_path, password):
    """Read and decrypt a password-protected PDF."""
    try:
        with open(file_path, 'rb') as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            # Check if the PDF is encrypted
            if pdf_reader.is_encrypted:
                pdf_reader.decrypt(password)  # Decrypt with the provided password

            # Extract text from all pages
            text = ''
            for page in pdf_reader.pages:
                text += page.extract_text()

            return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return None

def extract_transactions(file_path, password):
    """Extract transaction data from tables in the PDF."""
    try:
        transactions = []
        isRewardPointsInLast = "axis" in file_path
        with pdfplumber.open(file_path, password=password) as pdf:
            for page in pdf.pages:
                # Extract text from the page
                text = page.extract_text()
                if text:
                    lines = text.split("\n")  # Split text into lines
                    for line in lines:
                        # Match transaction lines using regex (customize as per your statement format)
                        match = re.match(r"(\d{2}/\d{2}/\d{4})", line)
                        if match and not isRewardPointsInLast:
                            # Split the string by spaces (or any separator used in your data)
                            hasCrDrInAmt = False
                            columns = line.split()
                            if(len(columns) < 2):
                                print("Less number of columns: ", line)

                            # Get the Date (first column)
                            date = columns[0]

                            # Get the Amount (last column)
                            amountStr = columns[-1].replace(',', '')
                            if "CR" in amountStr or "DR" in amountStr or "Cr" in amountStr or "Dr" in amountStr:
                                hasCrDrInAmt = True
                                if(len(re.sub(r'[^\d.-]', '', amountStr)) < 1):
                                    # read previous column
                                    amount = columns[-2].replace(',', '')
                                else:
                                    amount = re.sub(r'[^\d.-]', '', amountStr)
                            else:
                                amount = amountStr
                            if "CR" in amountStr or "Cr" in amountStr:
                                amount = '-' + amount

                            # Get the Reward Points (second last column, if it exists)
                            reward_points = columns[-2] if len(columns) > 2 else None
                            if hasCrDrInAmt:
                                reward_points = columns[-3]

                            # Get the Description (everything between the date and reward points)
                            description = " ".join(columns[1:-3]) if hasCrDrInAmt else " ".join(columns[1:-2])

                            transactions.append({"date": date, "details": description, "amount": float(amount),
                                                 "points": reward_points})
                        elif match and isRewardPointsInLast:
                            # Split the string by spaces (or any separator used in your data)
                            hasCrDrInAmt = False
                            columns = line.split()
                            if len(columns) < 2:
                                print("Less number of columns: ", line)

                            # Get the Date (first column)
                            date = columns[0]

                            # Get the Amount (last column)
                            amountStr = columns[-3].replace(',', '')
                            if "CR" in amountStr or "DR" in amountStr or "Cr" in amountStr or "Dr" in amountStr:
                                hasCrDrInAmt = True
                                if (len(re.sub(r'[^\d.-]', '', amountStr)) < 1):
                                    # read previous column
                                    amount = columns[-4].replace(',', '')
                                else:
                                    amount = re.sub(r'[^\d.-]', '', amountStr)
                            else:
                                amount = amountStr
                            if "CR" in amountStr or "Cr" in amountStr:
                                amount = '-' + amount

                            # Get the Reward Points (second last column, if it exists)
                            reward_points = columns[-1] if len(columns) > 2 else None
                            if hasCrDrInAmt:
                                reward_points = columns[-2]

                            # Get the Description (everything between the date and reward points)
                            description = " ".join(columns[1:-3]) if hasCrDrInAmt else " ".join(columns[1:-2])

                            transactions.append({"date": date, "details": description, "amount": float(amount),
                                                 "points": reward_points})

        return transactions
    except Exception as e:
        print(f"Error extracting transactions: {e}")
        return []

def process_transactions_with_variations(transactions):
    """Process and clean transaction data, handling variations in columns and formatting."""
    # Step 1: Convert to DataFrame
    df = pd.DataFrame(transactions)
    #df = normalize_columns(df)
    #df = normalize_amounts(df)

    # Step 4: Clean and format the DataFrame
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')  # Ensure 'amount' is numeric
    df.dropna(subset=['amount', 'details', 'date'], inplace=True)  # Remove rows with missing values
    #df['date'] = pd.to_datetime(df['date'], errors='coerce')  # Convert 'date' to datetime
    return df

def flag_issues(df, amount_threshold=500):
    """Identify potential issues in the transactions."""
    issues = []

    # Flag transactions above a certain amount
    large_transactions = df[df['amount'].abs() > amount_threshold]
    if not large_transactions.empty:
        issues.append("Large Transactions Found:\n" + large_transactions.to_string(index=False))

    # Check for duplicate transactions (same date, description, and amount)
    duplicates = df[df.duplicated(subset=["date", "details", "amount"], keep=False)]
    if not duplicates.empty:
        issues.append("Duplicate Transactions Found:\n" + duplicates.to_string(index=False))

    # Look for fees or charges (e.g., "Fee" in the description)
    fees = df[df['details'].str.contains('fee', case=False, na=False)]
    if not fees.empty:
        issues.append("Fees Found:\n" + fees.to_string(index=False))


    EMIs = df[df['details'].str.contains('emi', case=False, na=False)]
    if not EMIs.empty:
        issues.append("EMIs Found:\n" + EMIs.to_string(index=False))

    return issues

def alert_issues(issues):
    """Print identified issues to the console."""
    if issues:
        print("\nALERTS:")
        for issue in issues:
            print(issue)
    else:
        print("No issues found in the statement.")

def analyze_statement_with_variations(file_path, password, amount_threshold=500):
    """Complete workflow to analyze a bank statement."""
    # Step 1: Extract transactions
    transactions = extract_transactions(file_path, password)

    if not transactions:
        print("No transactions found.")
        return

    # Step 2: Process transactions
    try:
        df = process_transactions_with_variations(transactions)
        #print(df.head())
    except ValueError as e:
        print(f"Error processing statement: {e}")
        return

    # Step 3: Identify issues
    issues = flag_issues(df, amount_threshold=amount_threshold)

    # Step 4: Alert the user
    alert_issues(issues)

# Main execution
if __name__ == "__main__":
    path = "/Users/cb-it-01-1878/Documents/pythons/statement analyser/"
    file_path = input("Enter the path to the bank statement PDF (if axis statement then must include axis keyword in path): ")
    password = input("Enter the password for the statement: ")
    amount_threshold = float(input("Enter the threshold amount to flag transactions (e.g., 500): "))
    analyze_statement_with_variations(file_path, password, amount_threshold)
