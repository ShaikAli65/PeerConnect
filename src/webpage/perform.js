// utitlities  : ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
const addr = 'ws://localhost:12260';
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
    var searched = searchbox.value;
    if (searched == "")
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
// +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
var wss = new WebSocket("ws://localhost:42055");
var DATA = "";
wss.addEventListener('message', (event) => {
    DATA = JSON.parse(event.data);
    console.log("profile data :", DATA)})
wss.addEventListener('open', () => {})
wss.addEventListener('close', () => {})

function initiate()
{
    let connectToCode_;
    connectToCode_ = new WebSocket(addr);
    main_division.style.display = "flex";
    form_group.style.display = "none";
    headertile.style.display = "flex";
    var selected_profile = {'content':{'admin':DATA.content.admin},'header':'selectedprofile','id':''};
    selected_profile.content.admin.CONFIGURATIONS.server_port = '45000';
    selected_profile.header = "selectedprofile";
    selected_profile.id = "";
    // selected_profile.content.admin.CONFIGURATIONS.server_port = '45000';
    wss.send(JSON.stringify(selected_profile));

    connectToCode_.addEventListener('open', (event) => {

        document.getElementById("senderbutton").addEventListener("click",
        function()
        {
            if (focusedUser == null)
            {
                console.log("focused :",focusedUser)
                document.getElementById("intial_view").textContent="Select a user to chat";
            }
            else
            {
                data = createmessage();
                connectToCode_.send(data);
                console.log("message sent :",data);
            }
        });
    });
    document.getElementById("Close Application").addEventListener("click",()=>{
        try {
            connect_r = new WebSocket(addr);
            connect_r.send(JSON.stringify({
                "header":" 'thisiscommandtocore",
                "content":"thisiscommandtocore_/!_reload",
                "id":""
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
    recievedataFromPython(connectToCode_);
}
function ping_currentuser_id_topython(touser="") {
    Connection.send(
        JSON.stringify({
            "header":"thisisacommand",
            "content":"connectuser",
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
function recievedataFromPython(connecttocode_)
{
    const connectToCode_ = connecttocode_;
    connectToCode_.addEventListener('message', (event) => {
        console.log('::Received message :', event.data);
        data = JSON.parse(event.data);
        if (data.header === "thisisacommand")
        {
            if (data.content == '0')
            {
                removeuser(data.id);
            }
            else
            {
                createUserTile(data.content+"(^)"+data.id);
            }
        }
        if (data.header === "thisismyusername")
        {
            display_name.textContent = data.content;
        }
        if (data.header === "thisismessage")
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
        "header":"thisisacommand",
        "content":"endprogram",
        id:""
    }));
    document.body.innerHTML = "<h1>Session Ended</h1>";
    document.body.style.display= "flex";
    document.body.style.alignItems = "center";
    document.body.style.justifyContent = "center";
    connection = null;
    document.title = "Chat Closed";
    if (typeof window.gc === 'function') {
        window.gc();
      }
}

function createUserTile(idin='') // idin is the id of the user to be added syntax : name(^)ipaddress
{
    var idin_=idin.split("(^)");
    document.getElementById("intial_view").textContent = "Click on Name to view chat";
    document.getElementById("sender").style.display = "flex";
    var newtile_ = document.createElement("div");
    var newview_ = document.createElement("div");
    newtile_.textContent = idin_[0];
    newtile_.id = "person_"+idin_[1];
    newtile_.className = "usertile";
    newview_.id = "viewer_"+idin_[1];
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
    var Content_ = document.getElementById("message").value;
    // console.log('::Message sent :', Content_);                                       //*debug
    if (Content_ === "")
        return false;
    if (Content_.substring(0,7).includes("file::"))
    {
        subDiv_.textContent = "U sent a file";
        subDiv_.className = "message";
        subDiv_.style.display = "flex";
        subDiv_.style.backgroundColor = "#92b892";
        subDiv_.style.alignItems = "center";
        subDiv_.style.justifyContent = "center";
        subDiv_.id = "message_" + countMessage[focusedUser.id];
        countMessage[focusedUser.id] += 1 ;
        var wrapperdiv_ = document.createElement("div");
        wrapperdiv_.appendChild(subDiv_);
        wrapperdiv_.className = "messagewrapper right";
        focusedUser.appendChild(wrapperdiv_); 
        return JSON.stringify({
                "header":"thisisafile",
                "content":Content_.split("file::")[1].trim().replaceAll('\"',''),
                "id":focusedUser.id.split("_")[1]
            });
    }
    if (Content_.substring(0,7).includes("dir::"))
    {
        subDiv_.textContent = "U sent a dir";
        subDiv_.className = "message";
        subDiv_.style.display = "flex";
        subDiv_.style.backgroundColor = "#92b892";
        subDiv_.style.alignItems = "center";
        subDiv_.style.justifyContent = "center";
        subDiv_.id = "message_" + countMessage[focusedUser.id];
        countMessage[focusedUser.id] += 1 ;
        var wrapperdiv_ = document.createElement("div");
        wrapperdiv_.appendChild(subDiv_);
        wrapperdiv_.className = "messagewrapper right";
        focusedUser.appendChild(wrapperdiv_); 
        if (document.getElementById("litestatus").checked)
        {
            document.getElementById("litestatus").checked = false;
            return JSON.stringify({
                "header":"thisisadirlite",
                "content":Content_.split("dir::")[1].trim().replaceAll('\"',''),
                "id":focusedUser.id.split("_")[1]
            });
        }
        return JSON.stringify({
                "header":"thisisadir",
                "content":Content_.split("dir::")[1].trim().replaceAll('\"',''),
                "id":focusedUser.id.split("_")[1]
            });
    }
    subDiv_.textContent = Content_;
    subDiv_.className = "message";
    subDiv_.id = "message_" + countMessage[focusedUser.id];
    countMessage[focusedUser.id] += 1 ;
    var wrapperdiv_ = document.createElement("div");
    wrapperdiv_.appendChild(subDiv_);
    wrapperdiv_.className = "messagewrapper right";
    focusedUser.appendChild(wrapperdiv_);
    focusedUser.scrollBy(0,100);
    document.getElementById("message").value="";
    trimmed = focusedUser.id.split("_")[1].split("~")
    return JSON.stringify({
                "header":"thisisamessage",
                "content":Content_,
                "id":focusedUser.id.split("_")[1]
            });
}

function recievedmessage(recievedata)
{
    console.log("::recievedata : ",recievedata);
    var reciever = recievedata.id.trim();
    recievedata = recievedata.content;
    console.log("::recievedata : ","person_",reciever);
    var reciever_tile = document.getElementById("person_"+reciever);
    if(reciever_tile == null)
    {
        reciever_tile = createUserTile("Unknown@"+reciever+"(^)"+reciever);
        reciever_tile.style.backgroundColor = "var(--dark)";
    }
    if(reciever_view != focusedUser)
    {
        reciever_tile.style.backgroundColor = "var(--dark)";
    }
    var reciever_view = document.getElementById("viewer_"+reciever);
    var wrapperdiv_ = document.createElement("div");
    var subDiv_ = document.createElement("div");
    reciever_view.scrollTo=reciever_view.scrollBy(0,100);
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
    // idin syntax : name(^)ipaddress
    var user_ = document.getElementById("person_"+idin);
    var userview_ = document.getElementById("viewer_"+idin);
    console.log("removing user :",user_," ",userview_," ",idin);
    division_alive.removeChild(user_);
    users_list.splice(users_list.indexOf(user_),1);
    initial_view.textContent = "Select a user to chat";
    if (focusedUser != userview_)
    {
        division_viewerpov.removeChild(userview_);
        console.log("line 340 focused :",focusedUser)
    }
    else
    {
        initial_view.style.display = "flex";
        division_viewerpov.appendChild(initial_view);
        console.log("line 346 focused :",focusedUser)

         userview_.textContent='User Lost !';
         focusedUser = null;
         division_viewerpov.removeChild(userview_);
    }
}
