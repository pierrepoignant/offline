I want to create a faire blueprint similar to netsuite

the sql to get from snowflake is @request.sql 

new table faire_data
faire_data.brand_id => map with brands.id using brand (which is code) from the sql
faire_data.customer_id => faire_customer_name map with channel_customers.name to match the customer. If the customer does not exists, need to create with channel_customers.brand_id = the brand_id from above, channel_customers.channel_id=11
faire_data.date => month
faire_data.item_id => FK to 
faire_data.revenues => faire_net_rev
faire_data.units => faire_net_units_sold
The line is unique with faire_data.brand_id / faire_data.customer_id / faire_data.date
