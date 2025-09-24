import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import time

# File path
EXCEL_FILE = "data.xlsx"

# Removing @st.cache_data to avoid caching issues
def load_data():
    sales = pd.read_excel(EXCEL_FILE, sheet_name="SalesLog")
    collections = pd.read_excel(EXCEL_FILE, sheet_name="Collections")
    assignments = pd.read_excel(EXCEL_FILE, sheet_name="Assignments")

    # Ensure numeric
    sales["QuotedPrice"] = pd.to_numeric(sales.get("QuotedPrice", 0), errors="coerce").fillna(0)
    sales["DepositPaid"] = pd.to_numeric(sales.get("DepositPaid", 0), errors="coerce").fillna(0)

    # Ensure collections fields are numeric
    collections["QuoteID"] = pd.to_numeric(collections.get("QuoteID", 0), errors="coerce")
    collections["DepositPaid"] = pd.to_numeric(collections.get("DepositPaid", 0), errors="coerce").fillna(0)

    # Ensure dates
    if "StartDate" in sales.columns:
        sales["StartDate"] = pd.to_datetime(sales["StartDate"], errors="coerce")

    # Ensure QuoteID column exists
    if "QuoteID" not in sales.columns:
        sales["QuoteID"] = pd.Series(dtype="int")

    # Normalize QuoteID columns to integers for matching  <-- ADD THIS
    sales["QuoteID"] = pd.to_numeric(sales["QuoteID"], errors="coerce").fillna(0).astype(int)
    collections["QuoteID"] = pd.to_numeric(collections["QuoteID"], errors="coerce").fillna(0).astype(int)

    return sales, collections, assignments

def save_data(sales, collections, assignments):
    retries = 3
    for attempt in range(retries):
        try:
            with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl", mode="w") as writer:
                sales.to_excel(writer, sheet_name="SalesLog", index=False)
                collections.to_excel(writer, sheet_name="Collections", index=False)
                assignments.to_excel(writer, sheet_name="Assignments", index=False)
            return  # ✅ Saved successfully
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(1)  # wait before retry
            else:
                st.error("⚠️ Could not save data. Please close 'data.xlsx' and try again.")

def sync_deposit_paid(sales, collections):
    # Sum all deposits by QuoteID in the Collections table
    deposit_sums = collections.groupby("QuoteID")["DepositPaid"].sum().reset_index()

    for _, row in deposit_sums.iterrows():
        quote_id = row["QuoteID"]
        total_paid = row["DepositPaid"]
        
        # Update DepositPaid based on the total sum of deposits for each QuoteID
        sales.loc[sales["QuoteID"] == quote_id, "DepositPaid"] = total_paid

    return sales



def update_balance_due(sales, collections):
    # Ensure numeric conversion of QuoteID and DepositPaid
    sales["QuoteID"] = pd.to_numeric(sales["QuoteID"], errors="coerce").fillna(0).astype(int)
    collections["QuoteID"] = pd.to_numeric(collections["QuoteID"], errors="coerce").fillna(0).astype(int)

    # Merge the collections with the sales data to bring in QuotedPrice and DepositPaid from sales
    merged = collections.merge(
        sales[["QuoteID", "QuotedPrice", "DepositPaid"]], on="QuoteID", how="left"
    )

    # Debug: Check the columns after merge
    
    # If columns are duplicated (DepositPaid_x, DepositPaid_y), use the correct ones
    if 'DepositPaid_x' in merged.columns and 'DepositPaid_y' in merged.columns:
        # Add up the DepositPaid values from both sales and collections
        merged['TotalDepositPaid'] = merged['DepositPaid_x'] + merged['DepositPaid_y']  # Sum of DepositPaid from both
        merged["BalanceDue"] = (merged["QuotedPrice"] - merged['TotalDepositPaid']).clip(lower=0) # BalanceDue = QuotedPrice - TotalDepositPaid
        
        # Update the collections' BalanceDue and DepositPaid based on the merged data
        collections["BalanceDue"] = merged["BalanceDue"]
        collections["DepositPaid"] = merged['DepositPaid_y']  # Keeping the correct DepositPaid from collections
        # If BalanceDue is 0, set DepositDue to 0 as well
        collections["DepositDue"] = collections.apply(
            lambda row: 0 if row["BalanceDue"] == 0 else (row["DepositDue"] if not pd.isna(row["DepositDue"]) else 0), axis=1
        )

        # Update the sales data with the new total DepositPaid
        for i, row in merged.iterrows():
            sales.loc[sales["QuoteID"] == row["QuoteID"], "DepositPaid"] = row["TotalDepositPaid"]
            
            # Update Deposit% in sales log based on new DepositPaid
            quoted_price = row["QuotedPrice"]
            deposit_paid = row["TotalDepositPaid"]
            deposit_pct = round((deposit_paid / quoted_price) * 100, 2) if quoted_price > 0 else 0.0
            sales.loc[sales["QuoteID"] == row["QuoteID"], "Deposit%"] = deposit_pct

    else:
        st.error("Error: Missing 'DepositPaid' or 'QuotedPrice' columns in the merged DataFrame.")
    
    # Return updated collections
    return collections



def safe_rerun():
    try:
        st.experimental_rerun()
    except AttributeError:
        # Fallback: force rerun by setting session state and stopping app
        st.session_state["force_rerun"] = not st.session_state.get("force_rerun", False)
        st.stop()

# Then call safe_rerun() instead of st.experimental_rerun()



# Load data initially
sales, collections, assignments = load_data()
sales = sync_deposit_paid(sales, collections)
collections = update_balance_due(sales, collections)

# Sidebar
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Sales Log", "Collections", "Assignments"])

# ---------------- Dashboard ----------------
if page == "Dashboard":
    st.title("📊 Dashboard")

    # ---- Filters ----
    st.sidebar.subheader("Filters")

    # Sales Rep Filter
    reps = ["All"] + sorted(sales["SalesRep"].dropna().unique().tolist())
    selected_rep = st.sidebar.selectbox("Select Sales Rep", reps)

    # Date Range Filter
    if "StartDate" in sales.columns and pd.api.types.is_datetime64_any_dtype(sales["StartDate"]):
        valid_dates = sales["StartDate"].dropna()
        if not valid_dates.empty:
            min_date = valid_dates.min().date()
            max_date = valid_dates.max().date()
            date_range = st.sidebar.date_input("Select Date Range", [min_date, max_date])
            if isinstance(date_range, list) and len(date_range) == 2:
                start_date, end_date = date_range
            else:
                start_date, end_date = min_date, max_date
        else:
            start_date, end_date = None, None
    else:
        start_date, end_date = None, None

    # Apply Filters
    filtered_sales = sales.copy()
    if selected_rep != "All":
        filtered_sales = filtered_sales[filtered_sales["SalesRep"] == selected_rep]
    if start_date and end_date:
        filtered_sales = filtered_sales[
            (filtered_sales["StartDate"] >= pd.to_datetime(start_date)) & 
            (filtered_sales["StartDate"] <= pd.to_datetime(end_date))
        ]

    # Filter to get only won jobs
    won_sales = filtered_sales[filtered_sales["Status"] == "Won"]
    won_sales["QuoteID"] = pd.to_numeric(won_sales["QuoteID"], errors="coerce").fillna(0).astype(int)

    # Filter collections matching won sales
    filtered_collections = collections[collections["QuoteID"].isin(won_sales["QuoteID"])]

    # Calculate totals
    total_revenue_won = won_sales["QuotedPrice"].sum()
    total_deposit_won = won_sales["DepositPaid"].sum()
    balance_due_won_jobs = (won_sales["QuotedPrice"] - won_sales["DepositPaid"]).sum()
    total_collections_won = filtered_collections["DepositPaid"].sum()

    # ---- KPIs ----
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Quotes Sent", len(filtered_sales))
    col2.metric("Jobs Won", len(won_sales))
    col3.metric("Jobs Pending", len(filtered_sales[filtered_sales["Status"] == "Sent"]))
    col4.metric("Jobs Lost", len(filtered_sales[filtered_sales["Status"] == "Lost"]))

    col5, col6, col7, col8 = st.columns(4)
    if len(filtered_sales) > 0:
        win_rate = (len(won_sales) / len(filtered_sales)) * 100
    else:
        win_rate = 0

    col5.metric("Win Rate %", f"{win_rate:.1f}%")

    col6.metric("Closed $", f"${total_revenue_won:,.0f}")
    col7.metric("Deposits Paid", f"${total_deposit_won:,.0f}")
    col8.metric("Balance Due", f"${balance_due_won_jobs:,.0f}")  # Updated balance due
    # Assigned and Pending Tasks KPI

    st.metric("Total Collected (Collections)", f"${total_collections_won:,.0f}")
    
   


    

    # ---- Charts ----
    # Calculate revenue by status for filtered sales (only for statuses Sent, Won, Lost)
    revenue_by_status = filtered_sales.groupby("Status")["QuotedPrice"].sum()

    # Calculate total revenue to get percentages
    total_revenue = revenue_by_status.sum()

    # Calculate percentage revenue by each status
    revenue_pct = (revenue_by_status / total_revenue) * 100 if total_revenue > 0 else 0

    st.subheader("Revenue Breakdown")

    fig, ax = plt.subplots()

    if total_revenue > 0:
        bars = ax.bar(
            revenue_by_status.index,
            revenue_by_status.values,
            color=[
                "green" if status == "Won" else "orange" if status == "Lost" else "blue"
                for status in revenue_by_status.index
            ],
        )
        # Add percentage labels on top of bars
        for bar, pct in zip(bars, revenue_pct):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, height, f"{pct:.1f}%", ha="center", va="bottom")

        ax.set_ylabel("Revenue ($)")
        ax.set_title("Revenue Breakdown by Status")
        st.pyplot(fig)
    else:
        st.warning("No revenue data available for the selected filters.")

    st.subheader("Payments Overview")
    fig2, ax2 = plt.subplots()
    if total_deposit_won > 0 or balance_due_won_jobs > 0 or total_collections_won > 0:
        payments_data = {
            "Deposits Paid": total_deposit_won,
            "Balance Due": balance_due_won_jobs,
            "Collections": total_collections_won,
        }

        total_payments = total_deposit_won + balance_due_won_jobs + total_collections_won
        payment_percentages = {key: value / total_payments * 100 for key, value in payments_data.items()}

        labels = [f"{k} ({v:.1f}%)" for k, v in payment_percentages.items()]

        pd.Series(payments_data).plot(
            kind="bar", ax=ax2, color=["blue", "purple", "green"]
        )
        ax2.set_title("Payments Tracking (Won Jobs Only)")
        ax2.set_xticklabels(labels, rotation=45)
        st.pyplot(fig2)
    else:
        st.warning("No payment data available for the selected filters.")
        
        # Assigned and Pending Tasks KPI
    assigned_tasks = assignments["QuoteID"].unique()  # Get assigned QuoteIDs from the Assignments dataframe
    all_quote_ids = sales["QuoteID"].unique()  # Get all QuoteIDs from the SalesLog dataframe

    # Filter for pending tasks (tasks that do not have assignments yet)
    pending_tasks = [quote_id for quote_id in all_quote_ids if quote_id not in assigned_tasks]

    # Add metrics for assigned and pending tasks
    col9, col10 = st.columns(2)
    col9.metric("Assigned Tasks", len(assigned_tasks))  # Number of assigned tasks
    col10.metric("Pending Tasks", len(pending_tasks))  # Number of pending tasks

    # Create a simple bar chart for Assigned vs Pending tasks
    fig3, ax3 = plt.subplots()
    task_counts = [len(assigned_tasks), len(pending_tasks)]  # Counts of assigned and pending tasks
    task_labels = ['Assigned', 'Pending']  # Labels for the bar chart
    ax3.bar(task_labels, task_counts, color=['green', 'red'])

    ax3.set_title("Assigned vs Pending Tasks")
    ax3.set_ylabel("Number of Tasks")
    st.pyplot(fig3)


# ---------------- Sales Log ----------------
elif page == "Sales Log":
    st.title("📝 Sales Log")

    # Initialize session state inputs if not present
    if "quoted_price_input" not in st.session_state:
        st.session_state.quoted_price_input = 0.0
    if "deposit_paid_input" not in st.session_state:
        st.session_state.deposit_paid_input = 0.0

    # Show success message and ask if want to add another sale
    if "sale_added" in st.session_state and st.session_state["sale_added"] is not None:
        st.success(f"Sale added successfully! (Quote ID: {st.session_state['sale_added']})")

        add_another = st.radio("Would you like to add another sale?", ["No", "Yes"], index=0)

        if add_another == "Yes":
            # Clear session to show form again immediately
            st.session_state["sale_added"] = None
        else:
            st.subheader("All Sales Entries")
            st.dataframe(sales)

    # If no sale added or user selected "Yes" to add another
    if st.session_state.get("sale_added") is None:
        quoted_price = st.number_input("Quoted Price *", min_value=0.0, format="%.2f", key="quoted_price_input")
        deposit_paid = st.number_input("Deposit Paid *", min_value=0.0, format="%.2f", key="deposit_paid_input")

        if quoted_price > 0:
            deposit_pct = round((deposit_paid / quoted_price) * 100, 2)
        else:
            deposit_pct = 0.0

        st.text(f"Deposit %: {deposit_pct:.2f}%")

        with st.form("add_sale"):
            st.subheader("Add New Sale")
            client = st.text_input("Client *")
            status = st.selectbox("Status *", ["Sent", "Won", "Lost"])
            sales_rep = st.text_input("Sales Rep *")
            start_date = st.date_input("Start Date *")
            end_date = st.date_input("End Date *")
            job_type = st.text_input("Job Type *")

            submitted = st.form_submit_button("Add Sale")

            if submitted:
                quoted_price_val = st.session_state.get("quoted_price_input", 0.0)
                deposit_paid_val = st.session_state.get("deposit_paid_input", 0.0)

                if not client or not sales_rep or not job_type:
                    st.error("⚠️ All fields are required. Please fill them in.")
                else:
                    if quoted_price_val > 0:
                        deposit_pct = round((deposit_paid_val / quoted_price_val) * 100, 2)
                    else:
                        deposit_pct = 0.0

                    if "QuoteID" in sales.columns and not sales["QuoteID"].dropna().empty:
                        last_id = pd.to_numeric(sales["QuoteID"], errors="coerce").max()
                        new_id = int(last_id) + 1 if pd.notnull(last_id) else 1001
                    else:
                        new_id = 1001

                    new_row = {
                        "QuoteID": new_id,
                        "Client": client,
                        "QuotedPrice": quoted_price_val,
                        "Status": status,
                        "SalesRep": sales_rep,
                        "Deposit%": deposit_pct,
                        "DepositPaid": deposit_paid_val,
                        "StartDate": start_date,
                        "EndDate": end_date,
                        "JobType": job_type
                    }

                    sales = pd.concat([sales, pd.DataFrame([new_row])], ignore_index=True)
                    save_data(sales, collections, assignments)

                    sales, collections, assignments = load_data()
                    st.session_state["sale_added"] = new_id
                    safe_rerun()

        st.subheader("All Sales Entries")
        st.dataframe(sales)




# ---------------- Collections ----------------
# --- inside Collections page ---
elif page == "Collections":
    st.title("💰 Collections")

     # Step 1: If collection just added, show success + ask for another
    if "collection_added_quote" in st.session_state and st.session_state["collection_added_quote"] is not None:
        st.success(f"✅ Collection successfully added for Quote ID {st.session_state['collection_added_quote']}")

        add_another = st.radio("Would you like to add another collection?", ["No", "Yes"], index=0)
        
        if add_another == "No":
            st.subheader("All Collections Data")
            st.dataframe(collections)
            st.stop()  # Stop here — don't show form
        else:
            # Reset flags for next collection
            st.session_state["collection_added_quote"] = None
            st.session_state.pop("collection_submitted", None)


    won_sales = sales[sales["Status"] == "Won"]
    options = ["Select a QuoteID or Client"] + [
        f"{row['QuoteID']} - {row['Client']}" for _, row in won_sales.iterrows()
    ]
    selected = st.selectbox("Search QuoteID or Client", options, index=0)

    if selected != "Select a QuoteID or Client":
        selected_quote_id = int(selected.split(" - ")[0])
        # Get total deposit paid so far from sales log (should include initial deposit + synced collections)
        total_deposit_paid_so_far = sales.loc[sales["QuoteID"] == selected_quote_id, "DepositPaid"].values[0]
        quoted_price = won_sales.loc[won_sales["QuoteID"] == selected_quote_id, "QuotedPrice"].values[0]

        remaining_balance_due = quoted_price - total_deposit_paid_so_far
        existing_collection = collections[collections["QuoteID"] == selected_quote_id]

        with st.form("update_collection"):
            st.write(f"Remaining Balance Due: ${remaining_balance_due:.2f}")
        
            deposit_paid_input = st.number_input("Deposit Paid", value=0.0, min_value=0.0, format="%.2f")
           

            status_input = st.selectbox(
                "Status",
                options=["Pending", "Partially Paid", "Paid", "Overdue"],
                index=(["Pending", "Partially Paid", "Paid", "Overdue"].index(existing_collection["Status"].iloc[0])
                    if not existing_collection.empty else 0)
            )

            submitted = st.form_submit_button("Save Collection")

            if submitted and not st.session_state.get("collection_submitted", False):
                st.session_state["collection_submitted"] = True
                
                # Get previous deposits made for the selected quote
                previous_deposit_paid = existing_collection["DepositPaid"].sum() if not existing_collection.empty else 0.0

                # Update deposit paid in the collections table
                if not existing_collection.empty:
                    idx = existing_collection.index[0]
                    # Update deposit with previous + new input
                    collections.at[idx, "DepositPaid"] = previous_deposit_paid + deposit_paid_input
                    collections.at[idx, "Status"] = status_input
                else:
                    new_row = {
                        "QuoteID": selected_quote_id,
                        "Client": won_sales.loc[won_sales["QuoteID"] == selected_quote_id, "Client"].values[0],
                        "DepositPaid": deposit_paid_input,
                        "Status": status_input,
                    }
                    collections = pd.concat([collections, pd.DataFrame([new_row])], ignore_index=True)

                # Sync deposit paid with SalesLog
                sales = sync_deposit_paid(sales, collections)

                # Recalculate the Deposit% for the quote in SalesLog
                for i, row in sales.iterrows():
                    if row["QuoteID"] == selected_quote_id:
                        quoted = row["QuotedPrice"]
                        paid = row["DepositPaid"]
                        deposit_pct = round((paid / quoted) * 100, 2) if quoted > 0 else 0.0
                        sales.at[i, "Deposit%"] = deposit_pct

                # Update the Balance Due in Collections after syncing
                collections = update_balance_due(sales, collections)

                # Save the updated data
                save_data(sales, collections, assignments)

                # Show success and rerun to trigger radio prompt
                st.session_state["collection_added_quote"] = selected_quote_id
                safe_rerun()



    st.subheader("All Collections Data")
    st.dataframe(collections)



# ---------------- Assignments ----------------
if page == "Assignments":
    st.title("📋 Assignments")

    # ---- Assigned and Pending Tasks KPI ----
    assigned_tasks = assignments["QuoteID"].unique()  # Get assigned QuoteIDs from the Assignments dataframe
    all_quote_ids = sales["QuoteID"].unique()  # Get all QuoteIDs from the SalesLog dataframe

    # Filter for pending tasks (tasks that do not have assignments yet)
    pending_tasks = [quote_id for quote_id in all_quote_ids if quote_id not in assigned_tasks]

    # Add metrics for assigned and pending tasks at the top of the Assignments section
    col1, col2 = st.columns(2)
    assigned_count = col1.metric("Assigned Tasks", len(assigned_tasks))  # Number of assigned tasks
    pending_count = col2.metric("Pending Tasks", len(pending_tasks))  # Number of pending tasks

    # ---- Button to show Task Tables ----
    if st.button("Show Assigned Tasks"):
        # Filter the tasks to show only assigned tasks
        assigned_task_data = assignments[assignments["QuoteID"].isin(assigned_tasks)]
        st.subheader("Assigned Tasks")
        st.dataframe(assigned_task_data)

    if st.button("Show Pending Tasks"):
        # Filter the tasks to show only pending tasks
        pending_task_data = sales[~sales["QuoteID"].isin(assigned_tasks)]  # Tasks that are not assigned
        st.subheader("Pending Tasks")
        st.dataframe(pending_task_data)

    # ---- Rest of the Assignments Section ----
    # Your existing code for displaying assignments goes here...

    # Your existing code for displaying assignments goes here...

    
    # Load the assignments data
    sales, collections, assignments = load_data()  # Reload data to ensure it's updated after save
    
    # Step 1: Show existing assignments below the form (without Client column)
    st.subheader("Assign Tasks")
    
    # Check if 'Client' column exists before dropping it
    if 'Client' in assignments.columns:
        assignments_display = assignments.drop(columns=["Client"])
    else:
        assignments_display = assignments  # If 'Client' column doesn't exist, display as is
    
    
    # Step 2: Assignment Form (for new tasks)
    # Create a session state variable to track if task has been assigned
    if 'assigned' not in st.session_state:
        st.session_state.assigned = False

    # Step 3: If task is assigned, show the radio button
    if st.session_state.assigned:
        assign_another = st.radio("Do you want to assign another task?", options=["Yes", "No"])

        if assign_another == "No":
            st.write("You have chosen not to assign any more tasks.")
            st.session_state.assigned = False  # Reset the assigned state
        elif assign_another == "Yes":
            st.write("You can now assign another task.")
            st.session_state.assigned = False  # Reset the assigned state to show the form again

    # Form for task assignment
    if not st.session_state.assigned:
        with st.form("assign_task"):
            # Dropdown for selecting either QuoteID or Client
            options = ["Select Quote ID or Client"] + [
                f"{row['QuoteID']} - {row['Client']}" for _, row in sales.iterrows()
            ]
            selected_option = st.selectbox("Search QuoteID or Client", options, index=0)

            # Check if the selection is valid and extract QuoteID and Client info
            if selected_option != "Select Quote ID or Client":
                if "-" in selected_option:
                    # Extract QuoteID and Client from the selected option
                    quote_id = int(selected_option.split(" - ")[0])
                    client = selected_option.split(" - ")[1]
                else:
                    quote_id = None
                    client = None
            else:
                quote_id = None
                client = None

            # Crew and Task Info
            crew_member = st.text_input("Crew Member")  # Name of the crew
            start_date = st.date_input("Start Date")
            end_date = st.date_input("End Date")
            payment = st.number_input("Crew Payment", min_value=0.0, format="%.2f")

            # Calculate days taken
            days_taken = (end_date - start_date).days if end_date and start_date else 0

            # Show days taken
            st.text(f"Days Taken: {days_taken} days")

            # Submit button
            submitted = st.form_submit_button("Assign Task")

            if submitted:
                # Check if all fields are filled
                if not crew_member:
                    st.error("⚠️ Please enter the Crew Member name.")
                elif quote_id is None:
                    st.error("⚠️ Please select a valid Quote ID or Client.")
                else:
                    # Add the new assignment to the assignments DataFrame
                    new_assignment = {
                        "QuoteID": quote_id,
                        "Client": client,  # Keep "Client" for reference, but we'll hide it
                        "CrewMember": crew_member,
                        "StartDate": start_date,
                        "EndDate": end_date,
                        "Payment": payment,
                        "DaysTaken": days_taken
                    }

                    assignments = pd.concat([assignments, pd.DataFrame([new_assignment])], ignore_index=True)
                    
                    # Save the updated assignments to Excel
                    save_data(sales, collections, assignments)

                    # Show success message
                    st.success(f"Task assigned to {crew_member} for Quote ID {quote_id} successfully!")
                    
                    # Reload the data to ensure the new task is displayed in the table below
                    sales, collections, assignments = load_data()

                    # Step 4: Mark as assigned and stop showing the form
                    st.session_state.assigned = True  # Task has been assigned

                    # Display updated assignments (without Client column)
                    st.subheader("Updated Assignments")
                    
                    # Check if 'Client' column exists again before dropping
                    if 'Client' in assignments.columns:
                        assignments_display = assignments.drop(columns=["Client"])
                    else:
                        assignments_display = assignments  # Display as is if no 'Client' column
                    
                    st.dataframe(assignments_display)  # Show the latest assignments

                    # After the task is assigned and the message is shown, the radio button will appear
                    st.session_state.assigned = True  # The radio button should show after task assignment

                    # Rerun the app to update the UI
                    safe_rerun()

    # Step 4: No need to show "Current Assignments" separately here, as it's shown after the form


    # Step 4: No need to show "Current Assignments" separately here, as it's shown after the form

        
    #st.subheader("Current Assignments")
    #st.dataframe(assignments)
    
    # Step 3: No need to show "Current Assignments" separately here, as it's shown after the form
