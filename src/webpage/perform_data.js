// utitlities  : ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
const addr = "ws://localhost:57976";
let focusedUser        =   document.getElementById(       ""      );
let initial_view       =   document.getElementById( "intial_view" );
let main_division      =   document.getElementById("main_division");
let form_group         =   document.getElementById( "form_group"  );
let display_name       =   document.getElementById( "display_name");
let division_alive     =   document.getElementById( "alive_users" );
let division_viewerpov =   document.getElementById(   "prattle"   );
let searchbox          =   document.getElementById(   "search"    );
let headertile         =   document.getElementById( "headertile"  );
let viewname           =   document.getElementById("currentviewing");
let Usersviews     =   [];
let countMessage   =   {};
let users_list     =   [];
let EventListeners =   [];
let Connection     =   null;
function searchfunction()
{
    const searched = searchbox.value;
    if (searched === "")
        return false;
    users_list.forEach(element => {
        if (element.textContent.toLowerCase().includes(searched.toLowerCase()))
            element.style.display = "flex";
        else
            element.style.display = "none";
    }
    );
}

function eventlisteners()
{
    document.getElementById("message").addEventListener("keyup", function(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            document.getElementById("senderbutton").click();
        }
    });
    EventListeners.push(document.getElementById("message"));
    window.addEventListener('beforeunload', function(event) {
        endsession(Connection);
    });

}

// ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
document.getElementById('proceedBtn').addEventListener('click', () => {
    initiate_data();
});
function initiate_data()
{
    console.log("::initiating data",document.getElementById("proceed_flag"));
    if (document.getElementById("proceed_flag") == null)
    {
        return false;
    }
    let connectToCode_;
    connectToCode_ = new WebSocket(addr);
    main_division.style.display = "flex";
    form_group.style.display = "none";
    headertile.style.display = "flex";

    connectToCode_.addEventListener('open', (event) => {

        document.getElementById("senderbutton").addEventListener("click",
        function()
        {
            let data;
            if (focusedUser == null) {
                console.log("focused :", focusedUser)
                document.getElementById("intial_view").textContent = "Select a user to chat";
            } else {
                data = createmessage();
                connectToCode_.send(data);
                console.log("message sent :", data);
            }
        });
    });
    document.getElementById("Close Application").addEventListener("click",()=>{
        let connect_r;
        try {
            connect_r = new WebSocket(addr);
            connect_r.send(JSON.stringify({
                "header": 'this is a command',
                "content": "this is command to core_/!_reload",
                "id": ""
            }));
            connectToCode_ = connect_r;
        } catch (error) {
            endsession(connectToCode_);
        }
    });
    connectToCode_.addEventListener('close', (event) => {
        endsession(connectToCode_);
    });
    EventListeners.push(document.getElementById("senderbutton"));
    /*sending messages on port :12346 message syntax : "thisisamessage_/!_" + Content + "~^~" + focusedUser.id */
    eventlisteners();
    recieveDataFromPython(connectToCode_);
}
function ping_currentuser_id_topython(touser="") {
    Connection.send(
        JSON.stringify({
            "header":"this is a command",
            "content":"connect user",
            "id":touser
        })
    );
}
function revert()
{
    users_list.forEach(element => {
            element.style.display = "flex";
    });
}
function recieveDataFromPython(connecttocode_)
{
    const connectToCode_ = connecttocode_;
    connectToCode_.addEventListener('message', (event) => {
        console.log('::Received message :', event.data);
        let data = JSON.parse(event.data);
        if (data.header === "this is a command")
        {
            if (data.content == 0)
            {
                removeuser(data.id);
            }
            else
            {
                createUserTile(data.content, data.id);
            }
        }
        if (data.header == "this is my username")
        {
            display_name.textContent = data.content;
            document.title = data.content.split('(^)')[0];
        }
        if (data.header == "this is a message")
        {
            recievedmessage(data);
        }});
    /* data syntax : thisisamessage_/!_message~^~recieverid syntax of recieverid :
        name(^)ipaddress
       command syntax : f'thisisacommand_/!_{status}_/!_{peer.username}(^){peer.uri}'
    */
   Connection = connectToCode_;
}
function endsession(connection)
{
    // EventListeners.forEach(element => {
    //     element.removeEventListener("click",function(){});
    // });
    connection.send(JSON.stringify({
        "header":"this is a command",
        "content":"end program",
        id:""
    }));
    document.body.innerHTML = "<h1>Session Ended</h1>";
    document.body.style.display= "flex";
    document.body.style.alignItems = "center";
    document.body.style.justifyContent = "center";
    connection = null;
    document.title = "Chat Closed";
}

function createUserTile(name, name_id) // idin is the id of the user to be added syntax : name(^)ipaddress
{
    document.getElementById("intial_view").textContent = "Click on Name to view chat";
    document.getElementById("sender").style.display = "flex";
    var newtile_ = document.createElement("div");
    var newview_ = document.createElement("div");
    newtile_.textContent = name;
    newtile_.id = "person_"+name_id;
    newtile_.className = "usertile";
    newview_.id = "viewer_"+name_id;
    newview_.className = "viewer division";
    newview_.style.display = "none";
    newtile_.addEventListener("click",function(){showcurrent(newview_)});
    EventListeners.push(newtile_);
    division_alive.appendChild(newtile_);
    division_viewerpov.appendChild(newview_);
    Usersviews.push(newview_);
    users_list.push(newtile_);
    return newtile_;
}

function showcurrent(user)
{
    var nametile_ = document.getElementById("person_"+user.id.split("_")[1]);
    nametile_.style.backgroundColor = "";
    document.getElementById("intial_view").style.display="none";
    if (focusedUser != null)
    {
        focuseduser_viewer_pane = document.getElementById("viewer_"+focusedUser.id.split("_")[1]);
        focuseduser_viewer_pane.style.display = "none";
        console.log("line 209 focused :",focusedUser)

    }
    ping_currentuser_id_topython(user.id.split("_")[1]);
    user.style.display = "flex";
    user.style.backgroundColor = "";
    focusedUser = user;
    viewname.textContent = nametile_.textContent;
    console.log("line 217 focused :",focusedUser)

}

function createmessage()
{
    var subDiv_ = document.createElement("div");
    subDiv_.className = "message";
    subDiv_.style.display = "flex";
    subDiv_.style.alignItems = "center";
    subDiv_.style.justifyContent = "center";
    subDiv_.id = "message_" + countMessage[focusedUser.id];
    countMessage[focusedUser.id] += 1 ;
    let wrapperdiv_ = document.createElement("div");
    wrapperdiv_.appendChild(subDiv_);
    wrapperdiv_.className = "messagewrapper right";
    let Content_ = document.getElementById("message").value;
    if (Content_ === "")
        return false;
    if (Content_.substring(0,7).includes("file::"))
    {
        subDiv_.style.backgroundColor = "#92b892";
        document.getElementById("message").value="";
        focusedUser.appendChild(wrapperdiv_);
        Content_ = Content_.split("file::")[1].trim().replaceAll('\"','');
        subDiv_.textContent = "U sent a file : " + Content_;
        return JSON.stringify({
            "header":"this is a file",
            "content":{'files':[Content_,], 'grouping_level':4},
            "id":focusedUser.id.split("_")[1]
        });
    }
    if (Content_.substring(0,7).includes("dir::"))
    {
        focusedUser.appendChild(wrapperdiv_);
        document.getElementById("message").value="";
        Content_ = Content_.split("dir::")[1].trim().replaceAll('\"','')
        subDiv_.textContent = "U sent a dir: " + Content_;
        return JSON.stringify({
            "header":"this is a dir",
            "content":Content_,
            "id":focusedUser.id.split("_")[1]
        });
    }
    subDiv_.textContent = Content_;
    focusedUser.scrollBy(0,100);
    document.getElementById("message").value="";
    trimmed = focusedUser.id.split("_")[1].split("~");
    focusedUser.appendChild(wrapperdiv_)
    return JSON.stringify({
                "header":"this is a message",
                "content":Content_,
                "id":focusedUser.id.split("_")[1]
            });
}

function recievedmessage(recievedata)
{
    let reciever = recievedata.id.trim();
    let reciever_view = document.getElementById("viewer_"+reciever);
    console.log("::recievedata : ",recievedata);
    recievedata = recievedata.content;
    console.log("::recievedata : ","person_",reciever);
    let reciever_tile = document.getElementById("person_" + reciever);
    if(reciever_tile == null)
    {
        reciever_tile = createUserTile("Unknown@"+reciever);
        reciever_tile.style.backgroundColor = "var(--dark)";
    }
    if(reciever_view !== focusedUser)
    {
        reciever_tile.style.backgroundColor = "var(--dark)";
    }
    let wrapperdiv_ = document.createElement("div");
    let subDiv_ = document.createElement("div");
    // reciever_view.scrollBy(0,100);
    reciever_view.scrollTop = reciever_view.scrollHeight;
    subDiv_.textContent =recievedata;
    subDiv_.className="message";
    subDiv_.id = "message_"+countMessage;
    wrapperdiv_.className="messagewrapper left";
    wrapperdiv_.appendChild(subDiv_);
    reciever_view.appendChild(wrapperdiv_);
    countMessage++;
}
function removeuser(idin)
{
    const user_ = document.getElementById("person_" + idin);
    const userview_ = document.getElementById("viewer_" + idin);
    console.log("removing user :",user_," ",userview_," ",idin);
    division_alive.removeChild(user_);
    users_list.splice(users_list.indexOf(user_),1);
    initial_view.textContent = "Select a user to chat";
    if (focusedUser !== userview_)
    {
        division_viewerpov.removeChild(userview_);
    }
    else
    {
        initial_view.style.display = "flex";
        division_viewerpov.appendChild(initial_view);
         userview_.textContent='User Lost !';
         focusedUser = null;
         division_viewerpov.removeChild(userview_);
    }
}

// -------------------------profile data : ---------------------------------------------------
