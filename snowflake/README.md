snow connection test --account SWA87046-CT57250 --user pierre@goessor.com --private-key-path snowflake/private_key.p8

snow connection add \
  --connection-name essor \
  --account SWA87046-CT57250 \
  --user "pierre@goessor.com" \
  --authenticator SNOWFLAKE_JWT \
  --private-key-path /Users/pierrepoignant/Coding/offline/snowflake/private_key.p8 \
  --default
