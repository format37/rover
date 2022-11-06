# check is openai.token exists, then create it, with ask user to run token
if [ ! -f /home/openai/.openai/token ]; then
    # input token and save to file
    echo "Tokens are stored in https://beta.openai.com/account/api-keys"
    echo "Please input your token:"
    read token
    echo $token > openai.token
    echo "Token saved sucessfully!"
else
    echo "Token already exists!"
fi