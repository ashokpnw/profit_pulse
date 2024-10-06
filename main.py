import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
import os
import aiohttp
import asyncio
import random
import string
import numpy as np
import io
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import datetime
import pnwkit
import concurrent.futures
from db import DatabaseUser

# Load environment variables
load_dotenv()
TOKEN = os.getenv('TOKEN')
PNW_API_KEY = os.getenv('PNW_API_KEY')
kit = pnwkit.QueryKit(PNW_API_KEY)
LOG_CHANNEL_ID = os.getenv('log_channel')
AUTHORIZED_ROLE_ID = int(os.getenv('AUTHORIZED_ROLE_ID'))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
db = DatabaseUser()


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}!')
    await db.init_db()
    await bot.tree.sync()
    update_share_prices.start()
async def log_transaction(company_name: str, num_shares: int, share_price: float, total_value: float, user_id: str, transaction_type: str):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    
    if log_channel:
        log_message = (
            f"{transaction_type} Transaction Log:\n"
            f"User ID: {user_id}\n"
            f"Company: {company_name}\n"
            f"Shares {transaction_type}d: {num_shares}\n"
            f"Share Price: {share_price}\n"
            f"Total {transaction_type} Value: {total_value}\n"
            f"Time: {datetime.datetime.now().isoformat()}"
        )
        await log_channel.send(log_message)
    else:
        print(f"Log channel with ID {LOG_CHANNEL_ID} not found.")
        

async def generate_graph_in_background(company_name, times, prices, period):
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, lambda: create_and_save_graph(company_name, times, prices, period))

def create_and_save_graph(company_name, times, prices, period):
    # Create the plot
    plt.figure(figsize=(10, 5))

    # Plot with different colors based on price direction
    for i in range(1, len(prices)):
        if prices[i] > prices[i - 1]:
            plt.plot([times[i-1], times[i]], [prices[i-1], prices[i]], color='green', linewidth=2, marker='o')
        else:
            plt.plot([times[i-1], times[i]], [prices[i-1], prices[i]], color='red', linewidth=2, marker='o')

    # Format and style the graph
    plt.title(f"Share Price History for {company_name} ({period})")
    plt.xlabel('Time')
    plt.ylabel('Share Price')
    plt.grid(True)
    plt.xticks(rotation=45)

    # Adjust the x-axis to show only key time points, not cluttered data
    if period in ['1h', '12h']:
        plt.gca().xaxis.set_major_locator(plt.MaxNLocator(10))  # Adjust for shorter periods
    elif period in ['1d', '3d', '7d']:
        plt.gca().xaxis.set_major_locator(plt.MaxNLocator(6))  # Adjust for longer periods

    # Save the plot to a BytesIO object
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    return buf

@bot.tree.command(name="share_price_graph", description="Get a graph of share prices over a specific period.")
@app_commands.describe(company_name="Graph of the company", period="1h,12h,1d,3d,7d")
async def share_price_graph(interaction: discord.Interaction, company_name: str, period: str):
    await interaction.response.defer()
    try:
        price_data = await db.get_share_price_history(company_name, period)

        if not price_data:
            await interaction.followup.send(f"No price history found for {company_name}.", ephemeral=True)
            return

        times, prices = zip(*[(time, price) for date, time, price in price_data])

        buf = await generate_graph_in_background(company_name, times, prices, period)
        file = discord.File(fp=buf, filename=f"{company_name}_price_history.png")
        await interaction.followup.send(file=file)

    except Exception as e:
        await interaction.followup.send(f"An error occurred while generating the graph: {str(e)}", ephemeral=True)

@tasks.loop(minutes=1)
async def update_share_prices():
    # Fetch all companies
    companies = await db.get_all_companies()
    
    # Loop through all companies and record their current prices
    for company in companies:
        company_name = company[0]
        share_price = company[1]
        current_date = datetime.date.today().isoformat()
        current_time = datetime.datetime.now().strftime('%H:%M:%S')  # Get current time
        
        print(f"Storing {company_name} share price: {share_price} at {current_time}")
        
        # Store the current share price in history
        await db.store_share_price_history(company_name, current_date, current_time, share_price)

@bot.tree.command(name="ping", description="-")
async def ping(interaction: discord.Interaction):
    latency = bot.latency * 1000
    await interaction.response.send_message(f"pong! {latency:.1f}ms")

@bot.tree.command(name="who", description="Get nation information from Politics and War.")
@app_commands.describe(nation="Provide a nation ID, nation name, or mention a user to fetch their nation information.")
async def whois(interaction: discord.Interaction, nation: str):
    # Check if the identifier is a mention
    if nation.startswith("<@") and nation.endswith(">"):
        try:
            user_id = int(nation[2:-1])  # Convert mention to user ID
        except ValueError:
            await interaction.response.send_message("Invalid user mention.", ephemeral=True)
            return
        
        # Get the user's nation ID from the database
        nation_id = await db.get_user_data_by_user_id(user_id)
        if not nation_id:
            await interaction.response.send_message(f"User <@{user_id}> has not verified their nation ID yet. Please ask them to use the /verify command first.", ephemeral=True)
            return
    else:
        # Try to determine if the identifier is a nation ID (numeric) or nation name (string)
        if nation.isdigit():
            nation_id = int(nation)
        else:
            # Fetch nation by name
            query = kit.query("nations", {"nation_name": nation}, "id, nation_name")
            result = query.get()
            if not result or not result.nations:
                await interaction.response.send_message("Failed to fetch nation data by name. Please check the nation name and try again.", ephemeral=True)
                return
            nation_id = result.nations[0].id

    # Fetch the nation information from the Politics and War API using the nation ID
    query = kit.query("nations", {"id": int(nation_id)}, "id, nation_name")
    result = query.get()

    if not result or not result.nations:
        await interaction.response.send_message("Failed to fetch nation data. Please try again later.", ephemeral=True)
        return

    nation_name = result.nations[0].nation_name

    # Fetch balance and company shares information
    if await db.get_user_data_by_nation_id(nation_id):
        balance = round(await db.get_user_credits(await db.get_user_data_by_nation_id(nation_id)),2)
        companies = await db.get_all_companies()  # Assuming this returns a list of companies

        user_shares_info = ""  # This will store all the companies and shares info
        total_worth = 0  # To store the total worth of shares for all companies

        for company_data in companies:
            # Extract company name, share price, etc. Assuming company_data is structured like (company_name, share_price, ...)
            if isinstance(company_data, tuple):
                company_name = company_data[0]  # Extract the company name
                share_price = company_data[1]  # Extract the share price
            else:
                company_name = str(company_data)
                share_price = 0  # In case share price is missing, default to 0

            user_shares = await db.get_user_shares(user_id, company_name)
            
            # Calculate worth of the user's shares in this company
            company_worth = user_shares * share_price
            total_worth += company_worth  # Add to total worth across all companies

            if user_shares > 0:
                user_shares_info += (
                    f"🏢 **{company_name}**\n"
                    f"📊 **Shares Owned**: {user_shares}\n"
                    f"💰 **Worth**: ${company_worth:,.2f}\n"
                    f"🔖 **Share Price**: ${share_price:,.2f}\n\n"
                )
    else:
        balance = 'Not Registered'
        user_shares_info = 'No shares registered.'
        total_worth = 0

    # Create the first embedded message for nation details and balance
    embed1 = discord.Embed(title="Nation Information", color=discord.Color.blue())
    embed1.add_field(name="🌍 Nation Name", value=nation_name, inline=False)
    
    if balance != 'Not Registered':
        embed1.add_field(name="💵 Balance", value=f'<:CoinPulse:1279721599897178112> {balance:,}', inline=False)
        embed1.add_field(name="💼 Total Shares Worth", value=f'<:CoinPulse:1279721599897178112> {total_worth:,}', inline=False)
    else:
        embed1.add_field(name="💵 Balance", value=balance, inline=False)

    # Create the second embedded message for company shares details
    embed2 = discord.Embed(title="Company Shares", color=discord.Color.green())
    embed2.add_field(name="💡 Shares Info", value=user_shares_info or "No shares available", inline=False)

    # Send both embedded messages
    await interaction.response.send_message(embeds=[embed1, embed2])

@bot.tree.command(name="help", description="Shows a list of available commands.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Available Commands",
        description="Here are the commands you can use:",
        color=discord.Color.blue()
    )

    for command in bot.tree.get_commands():
        embed.add_field(
            name=f"/{command.name}",
            value=command.description or "No description",
            inline=False
        )

    try:
        await interaction.response.send_message(embed=embed)
    except discord.errors.InteractionResponded:
        print("Interaction has already been responded to.")

@bot.tree.command(name="verify", description="Verify your nation ID.")
async def verify_command(interaction: discord.Interaction, nation_id: int):
    user_id = str(interaction.user.id)

    # Check if the user is already registered
    stored_nation_id = await db.get_user_data_by_user_id(user_id)

    if stored_nation_id:
        await interaction.response.send_message(
            f"You are already registered with Nation ID: {stored_nation_id}.",
            ephemeral=True
        )
        return

    user = interaction.user.name
    query = kit.query("nations", {"id": int(nation_id)}, "id, nation_name, discord")
    result = query.get()

    if not result or not result.nations:
        await interaction.response.send_message("Failed to fetch nation data. Please try again later.", ephemeral=True)
        return

    nation_name = result.nations[0].nation_name
    discord = result.nations[0].discord
    
    if user == discord:
        # Store nation data in db
        await db.add_user(user_id, nation_id)
        await interaction.response.send_message("Registered successfully!")
    else:
        await interaction.response.send_message(f"Your nation Discord ({discord}) does not match your username ({user}).", ephemeral=True)


@bot.tree.command(name="add_credits", description="Add credits to a user's account.")
async def add_credits(interaction: discord.Interaction, user: discord.User, amount: int):
    # Check if the command invoker has the authorized role
    if AUTHORIZED_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    # Ensure amount is positive
    if amount <= 0:
        await interaction.response.send_message("Please enter a positive amount of credits.", ephemeral=True)
        return

    # Check if both the command user and mentioned user are registered
    command_user_registered = await db.get_user_data_by_user_id(interaction.user.id)
    mentioned_user_registered = await db.get_user_data_by_user_id(user.id)

    if not command_user_registered:
        await interaction.response.send_message("You are not registered with the bot. Please register first.", ephemeral=True)
        return

    if not mentioned_user_registered:
        await interaction.response.send_message(f"The mentioned user {user.mention} is not registered with the bot.", ephemeral=True)
        return

    # Add credits to the user
    await db.add_credits(user.id, amount)
    await interaction.response.send_message(f"Added {amount} credits to {user.mention}'s account.")

@bot.tree.command(name="register_company", description="Register a new company.")
@app_commands.describe(company_name="Name of the company", owner="Who owns the company", share_price="Initial share price", total_shares="Total number of shares")
async def register_company(interaction: discord.Interaction, company_name: str, owner:discord.User, share_price: float, total_shares: int):
    # Check if the company already exists
    existing_company = await db.get_company_by_name(company_name)
    if not any(role.id==AUTHORIZED_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permissions to remove.", ephemeral=True)
        return
    if existing_company:
        await interaction.response.send_message(f"Company `{company_name}` already exists.", ephemeral=True)
        return

    # Add the company to the database
    await db.add_company(company_name, share_price, total_shares, owner.id)
    await db.add_shares(company_name, total_shares)
    await interaction.response.send_message(f"Company `{company_name}` registered successfully with {total_shares} shares at {share_price} coins per share.")

@bot.tree.command(name="list_companies", description="List all registered companies.")
async def list_companies(interaction: discord.Interaction):
    companies = await db.get_all_companies()
    
    if not companies:
        await interaction.response.send_message("No companies are currently registered.", ephemeral=True)
        return

    embed = discord.Embed(title="Registered Companies", color=discord.Color.blue())
    
    for company_name, share_price, total_shares, user_id in companies:
        shares = await db.get_shares(company_name)
        percent = round((total_shares/shares)*100,2)
        valuation = round(shares * share_price,2)
        embed.add_field(
            name=f"Company: {company_name}",
            value=f"**Share Price**: <:CoinPulse:1279721599897178112>{share_price:,}\n**Registered Shares**: {shares}\n**Total Shares**: {total_shares}({percent}%)\n**Company Valuation**: ${valuation:,}\n**Owner**: <@{user_id}>",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="buy_shares", description="Buy shares in a company.")
@app_commands.describe(company_name="Name of the company to buy shares from.", num_shares="Number of shares you will buy")
async def buy_shares(interaction: discord.Interaction, company_name: str, num_shares: int):
    user_id = interaction.user.id

    try:
        # Fetch the company details
        company = await db.get_company_by_name(company_name)
        if not company:
            await interaction.response.send_message("Invalid company name.", ephemeral=True)
            return
        
        company_name, share_price, total_shares, company_owner_id = company

        # Check for order size limits
        MAX_SHARES_PER_TRANSACTION = 50  # Example limit
        if num_shares > MAX_SHARES_PER_TRANSACTION:
            await interaction.response.send_message(f"Cannot buy more than {MAX_SHARES_PER_TRANSACTION} shares in a single transaction.", ephemeral=True)
            return
        
        if total_shares < num_shares:
            await interaction.response.send_message(f"Not enough shares available. Available Shares: {total_shares}", ephemeral=True)
            return

        share_price = round(float(share_price), 2)
        total_cost = round(num_shares * share_price, 2)

        # Check if the user has enough balance
        user_balance = await db.get_user_credits(user_id)
        if user_balance < total_cost:
            await interaction.response.send_message("You don't have enough coins to buy these shares.", ephemeral=True)
            return

        # Update the user's shares and balance
        await db.update_user_shares(user_id, company_name, num_shares)
        await db.update_user_credits_after_purchase(user_id, total_cost)

        # Update the company's balance (add to the owner's credits)
        await db.add_credits(company_owner_id, total_cost)

        # Increase the share price slightly when shares are bought
        new_price = round(share_price * (1 + (num_shares / total_shares) ** 1.2), 2)
        new_shares = total_shares - num_shares
        await db.update_company_details(company_name, new_price, new_shares)

        # Log the transaction to a specific Discord channel
        await log_transaction(company_name, num_shares, share_price, total_cost, user_id, "Buy")

        await interaction.response.send_message(f"Successfully bought {num_shares} shares of {company_name} for {total_cost} coins.")
    
    except Exception as e:
        # Handle any errors that occur during the transaction
        await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

@bot.tree.command(name="sell_shares", description="Sell shares of a company.")
@app_commands.describe(company_name="Name of the company to sell shares from.", num_shares="Number of shares you want to sell")
async def sell_shares(interaction: discord.Interaction, company_name: str, num_shares: int):
    user_id = interaction.user.id

    # Fetch the company details
    company = await db.get_company_by_name(company_name)
    if not company:
        await interaction.response.send_message("Invalid company name.", ephemeral=True)
        return

    company_name, share_price, total_shares, company_owner_id = company
    share_price = round(float(share_price), 2)

    # Check if the user has enough shares to sell
    user_shares = await db.get_user_shares(user_id, company_name)
    if user_shares is None or user_shares < num_shares:
        await interaction.response.send_message("You don't have enough shares to sell.", ephemeral=True)
        return

    # Calculate the total value of the shares being sold
    total_value = round(num_shares * share_price, 2)

    # Update the user's shares and balance
    await db.update_user_shares(user_id, company_name, -num_shares)
    await db.add_credits(user_id, total_value)

    # Update the company's balance (deduct from the owner's credits)
    await db.update_user_credits_after_purchase(company_owner_id, total_value)

    # Reduce the share price slightly when shares are sold
    new_price = round(share_price * (1 - (num_shares / total_shares) ** 1.2), 2)
    new_shares = total_shares + num_shares
    await db.update_company_details(company_name, new_price, new_shares)

    # Log the transaction in the specified channel
    await log_transaction(company_name, -num_shares, share_price, total_value, user_id, "Sell")

    await interaction.response.send_message(f"Successfully sold {num_shares} shares of {company_name} for {total_value} coins.")
    
@bot.tree.command(name="remove_company", description="Remove a company from the database.")
@app_commands.describe(company_name="The name of the company to remove.")
async def remove_company_command(interaction: discord.Interaction, company_name: str):
    company = await db.get_company_by_name(company_name)
    if not any(role.id==AUTHORIZED_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permissions to remove.", ephemeral=True)
        return
    if not company:
        await interaction.response.send_message(f"Company {company_name} does not exist.")
        return

    await db.remove_company(company_name)
    await interaction.response.send_message(f"Company {company_name} and all related data have been removed.")
    
@bot.tree.command(name="edit_company", description="Edit company details.")
@app_commands.describe(company_name="Name of the company to edit", new_share_price="New share price", new_total_shares="New total number of shares")
async def edit_company(interaction: discord.Interaction, company_name: str, new_share_price: float, new_total_shares: int):
    # Check if the company exists
    company = await db.get_company_by_name(company_name)
    if not any(role.id==AUTHORIZED_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permissions to remove.", ephemeral=True)
        return
    if not company:
        await interaction.response.send_message(f"Company `{company_name}` does not exist.", ephemeral=True)
        return

    # Update the company's share price and total shares
    await db.update_company_details(company_name, new_share_price, new_total_shares)

    await interaction.response.send_message(f"Company `{company_name}` updated successfully. New price: {new_share_price} coins, New total shares: {new_total_shares}.")

@bot.tree.command(name="update_registered_shares",description="Updates the registered shares")
@app_commands.describe(company_name="Name of the company to edit", shares='Shares of the company')
async def update_registered_shares(interaction: discord.Interaction, company_name: str, shares: int):
    company = await db.get_company_by_name(company_name)
    if not any(role.id==AUTHORIZED_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permissions to remove.", ephemeral=True)
        return
    if not company:
        await interaction.response.send_message(f"Company `{company_name}` does not exist.", ephemeral=True)
        return
    await db.add_shares(company_name, shares)
    await interaction.response.send_message('Updated!')

@bot.tree.command(name='market', description="Show all available trades.")
async def market(interaction: discord.Interaction):
    trades = await db.get_all_trades()  # Fetch all available trades from the database

    if not trades:
        await interaction.response.send_message("No trades available.")
        return

    # Create an embed for displaying trades
    embed = discord.Embed(title="Available Trades", color=discord.Color.blue())

    for trade in trades:
        # Assuming the tuple is structured as (trade_id, seller_id, company_name, shares_available, price_per_share)
        trade_id = trade[0]
        seller_id = trade[1]
        company_name = trade[2]
        shares_available = trade[3]
        price_per_share = round(trade[4],2)

        embed.add_field(
            name=f"Trade ID: {trade_id}",
            value=(
                f"**Seller ID:** {seller_id}\n"
                f"**Company:** {company_name}\n"
                f"**Shares Available:** {shares_available}\n"
                f"**Price per Share:** ${price_per_share:,}"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="post_trade", description="Post a trade to sell shares on the market")
@app_commands.describe(company="Company to sell shares from", shares="Number of shares", price="Price per share", to="(Optional) User to send a direct trade to")
async def post_trade(interaction: discord.Interaction, company: str, shares: int, price: float, to: discord.User = None):
    user_id = interaction.user.id
    
    # Check if the user owns enough shares
    user_shares = await db.get_user_shares(user_id, company)
    if user_shares < shares:
        await interaction.response.send_message(f"You don't have enough shares to sell. You currently own {user_shares} shares of {company}.", ephemeral=True)
        return

    # If 'to' user is specified, it's a direct trade
    to_user_id = to.id if to else None

    # Post the trade in the market
    await db.create_trade(company, user_id, shares, price, to_user_id)
    
    if to_user_id:
        await interaction.response.send_message(f"Direct trade posted: Selling {shares} shares of {company} at ${price:,} per share to {to.mention}.")
    else:
        await interaction.response.send_message(f"Trade posted: Selling {shares} shares of {company} at ${price:,} per share.")

@bot.tree.command(name="buy_trade", description="Buy shares from the market")
@app_commands.describe(trade_id="ID of the trade to buy", num_shares="Number of shares to buy")
async def buy_trade(interaction: discord.Interaction, trade_id: int, num_shares: int):
    buyer_id = interaction.user.id
    
    # Get the trade details from the database
    trade = await db.get_trade(trade_id)
    if not trade:
        await interaction.response.send_message("Trade not found. Please check the trade ID.", ephemeral=True)
        return
    
    company_name = trade['company_name']
    shares_available = trade['shares_available']
    price_per_share = trade['price_per_share']
    seller_id = trade['seller_id']
    to_user_id = trade['to_user_id']  # New field to specify the direct trade recipient

    # If the trade is restricted to a specific user, check if the buyer is that user
    if to_user_id and to_user_id != buyer_id:
        await interaction.response.send_message(f"This trade is only available to <@{to_user_id}>.", ephemeral=True)
        return

    # Check if the requested number of shares is available
    if num_shares > shares_available:
        await interaction.response.send_message(f"Not enough shares available. Only {shares_available} shares are left.", ephemeral=True)
        return

    total_price = num_shares * price_per_share

    # Check if the buyer has enough credits
    buyer_credits = await db.get_user_credits(buyer_id)
    if buyer_credits < total_price:
        await interaction.response.send_message(f"You don't have enough credits to buy {num_shares} shares of {company_name}. Total cost is ${total_price:,}.", ephemeral=True)
        return
    
    # Transfer credits and shares
    await db.transfer_credits(buyer_id, seller_id, total_price)  # Transfer credits from buyer to seller
    await db.transfer_shares(seller_id, buyer_id, company_name, num_shares)  # Transfer shares from seller to buyer

    # Update or remove the trade from the market
    remaining_shares = shares_available - num_shares
    if remaining_shares > 0:
        # Update the trade to reflect the new number of available shares
        await db.update_trade(trade_id, remaining_shares)
    else:
        # Remove the trade from the market if no shares are left
        await db.delete_trade(trade_id)

    await interaction.response.send_message(f"Successfully bought {num_shares} shares of {company_name} from <@{seller_id}> for ${total_price:,}.", ephemeral=True)

bot.run(TOKEN)
