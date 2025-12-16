Whe import the CSV, please detect the format based on the CSV headers

Format Walmart if CSV headers include
walmart_calendar_week
walmart_item_number
item_name
pos_sales_this_year
pos_quantity_this_year
dollar_per_store_per_week_or_per_day_this_year
units_per_store_per_week_or_per_day_this_year
traited_store_count_this_year
repl_instock_percentage_this_year

Format CVS if CSV headers include
Time
Product
Total Sales $ WTD
Total Units WTD

Format Target if CSV headers include
Date
DPCI
Item Description
Sales $
Sales U
Sales $ PSPW
Sales U PSPW
OOS %

Format KeHe if CSV headers include
TIME FRAME
GEOGRAPHY
DESCRIPTION
Dollars
Units
Average Weekly Dollars Per Store Selling Per Item
Average Weekly Units Per Store Selling Per Item


Than import each line the following way

Format Walmart
sellthrough_data.channel_id = 2 
walmart_calendar_week => sellthrough_data.date => approach format is YYYYWW where WW is week number. You need to transform YYYYWW to the first monday of that week as a date
walmart_item_number => channel_items.channel_code (and sellthrough_data.channel_code) => approach look-up in the channel_items table. Should match channel_items.channel_code If do not exists, create the entry (also with channel_items.channel_name). If exists use the item_id for sellthrough_data.item_id
item_name => channel_items.channel_name
pos_sales_this_year => sellthrough_data.revenues => approach USD format
pos_quantity_this_year => sellthrough_data.units
dollar_per_store_per_week_or_per_day_this_year => sellthrough_data.usd_pspw
units_per_store_per_week_or_per_day_this_year => sellthrough_data.units_pspw
traited_store_count_this_year => sellthrough_data.stores
repl_instock_percentage_this_year => sellthrough_data.instock

Format Target
sellthrough_data.channel_id = 1
Date => sellthrough_data.date => approach Format is "Dec Wk 5 2024" where 5 is the week number. Transform into a date with the monday of that week
DPCI => channel_items.channel_code (and sellthrough_data.channel_code)
Item Description => channel_items.channel_name
Sales $ => sellthrough_data.revenues => approach USD format
Sales U => sellthrough_data.units
Sales $ PSPW => sellthrough_data.usd_pspw
Sales U PSPW => sellthrough_data.units_pspw
OOS % => sellthrough_data.oos

Format CVS
sellthrough_data.channel_id = 3
Time => sellthrough_data.date => approach Format is "Fiscal Week Ending 01-11-2025" where the date is the date of the week, need to change this to the monday (minus 6 days)
Product => channel_items.channel_code (and sellthrough_data.channel_code) => approach same logic as Walmart
Total Sales $ WTD => sellthrough_data.revenues => approach USD format
Total Units WTD => sellthrough_data.units

Format KeHe
TIME FRAME => Treat the first 5 digit as excel serial date to get the date of the week and convert to the monday of that week
GEOGRAPHY => sellthrough_data.channel_id => approach if equal to "EREWHON MARKETS - TOTAL US" than channel_id=76 if equal to "FRESH THYME MARKET - TOTAL US" than channel_id=77. If equal to "SPROUTS FARMERS MARKET - TOTAL US W/O PL" than channel_id=5
DESCRIPTION => channel_items.channel_code (and sellthrough_data.channel_code)
Dollars => sellthrough_data.revenues => approach USD format
Units => sellthrough_data.units
Average Weekly Dollars Per Store Selling Per Item => sellthrough_data.usd_pspw
Average Weekly Units Per Store Selling Per Item => sellthrough_data.units_pspw
