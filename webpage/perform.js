function initiate()
{
    var connectToCode_;
    connectToCode_ = new WebSocket('ws://localhost:12346');
    main_division.style.display = "flex";
    form_group.style.display = "none";
    headertile.style.display = "flex";
    connectToCode_.addEventListener('open', (event) => {

        document.getElementById("senderbutton").addEventListener("click",
        function()
        {
            if (focusedUser == null)
            {
                document.getElementById("intial_view").textContent="Select a user to chat";
            }
            else
            {
                connectToCode_.send(createmessage());
                console.log("message sent");
            }
        });

    });
    /*sending messages on port :12346 message syntax : "thisisamessage_/!_" + Content + "~^~" + focusedUser.id */
    eventlisteners();
    recievedataFromPython(connectToCode_);
}
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
function revert()
{
    users_list.forEach(element => {
            element.style.display = "flex";
    });
}
function recievedataFromPython(connecttocode_)
{
    var connectToCode_ = connecttocode_;
    connectToCode_.addEventListener('message', (event) => {
        var recievedata_ = event.data.split("_/!_");
        console.log('::Received message :', event.data);                                       //*debug
        if  (recievedata_[0] == "thisisamessage")
            recievedmessage(recievedata_[1]);
        else if (recievedata_[0] == "thisisausername")
            {
                createtile(recievedata_[1]);
            }
        else if (recievedata_[0] == "thisisafile")
        {
            recievedmessage(recievedata_[1])
        }
        else if (recievedata_[0] == 'thisisacommand')
        {
            removeuser(recievedata_[1]);
            console.log("::User leaving away :",recievedata_[1]);
        }
        else if (recievedata_[0] == "thisismyusername")
        {
            console.log("::Your user name :",recievedata_[1]);
            senderdetail = recievedata_[1];
            display_name.textContent = recievedata_[1];
        }
        else
            console.error('::Received unknown message :', event.data);                           //*debug
    });
    // window.addEventListener('beforeunload', function (event) {
    //     event.preventDefault();
    //     event.returnValue = '';
    //     connectToCode_.close();
    //   });
    // connectToCode_.addEventListener('close', (event) => {
    //     console.log('::Connection closed :', event.data);
    // });
    /* data syntax : thisisamessage_/!_message~^~recieverid syntax of recieverid :
     name(^)ipaddress using port 12346 to recieve
       data syntax : thisisausername_/!_name(^)ipaddress
    */
}

// utitlities  : ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

focusedUser        =   document.getElementById(       ""      );
initial_view       =   document.getElementById( "intial_view" );
main_division      =   document.getElementById("main_division");
form_group         =   document.getElementById( "form_group"  );
display_name       =   document.getElementById( "display_name");
division_alive     =   document.getElementById( "alive_users" );
division_viewerpov =   document.getElementById(   "prattle"   );
searchbox          =   document.getElementById(   "search"    );
headertile         =   document.getElementById( "headertile"  );
viewname           =   document.getElementById("currentviewing");
let senderdetail   =   "";
let Spwaned   =   [];
let countMessage   =   {};
let users_list     =   [];

// +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

function eventlisteners()
{
    document.getElementById("message").addEventListener("keyup", function(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            document.getElementById("senderbutton").click();
        }
    });


}

function createtile(idin='') // idin is the id of the user to be added syntax : name(^)ipaddress
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
    division_alive.appendChild(newtile_);
    division_viewerpov.appendChild(newview_);
    Spwaned.push(newview_);
    users_list.push(newtile_);
}

function showcurrent(user)
{
    var nametile_ = document.getElementById("person_"+user.id.split("_")[1]);
    nametile_.style.backgroundColor = "";
    document.getElementById("intial_view").style.display="none";
    for (var i = 0;i < Spwaned.length;i++ )
    {
        Spwaned[i].style.display = "none";
    }
    user.style.display = "flex";
    user.style.backgroundColor = ""
    focusedUser = user;
    viewname.textContent = nametile_.textContent;
}

function createmessage()
{
    var subDiv_ = document.createElement("div");
    var Content_ = document.getElementById("message").value;
    console.log('::Message sent :', Content_);                                       //*debug
    if (Content_ == "")
        return false;
    if (Content_.includes("file::"))
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
        return ("thisisafile_/!_"+Content_.split("::")[1]+"~^~" + focusedUser.id.split("_")[1]);
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
    return "thisisamessage_/!_" + Content_ + "~^~" + focusedUser.id.split("_")[1];
}

function recievedmessage(recievedata)
{
    console.log("::recievedata : ",recievedata.split("(^)"));
    var reciever = recievedata.split("(^)")[1];
    recievedata = recievedata.split("(^)")[0];
    console.log("::recievedata : ","person_",reciever);
    var recieverid_ = document.getElementById("person_"+reciever);
    if(recieverid_ == null)
    {
        console.error("::recieverid_ is null ",reciever);
        return false;
    }
    if(recieverid_ != focusedUser)
    {
        recieverid_.style.backgroundColor = "var(--dark)";
    }
    var wrapperdiv_ = document.createElement("div");
    var subDiv_ = document.createElement("div");
    var recieverview_ = document.getElementById("viewer_"+reciever);
    recieverview_.scrollTo=recieverview_.scrollBy(0,100);
    subDiv_.textContent =recievedata;
    subDiv_.className="message";
    subDiv_.id = "message_"+countMessage;
    wrapperdiv_.className="messagewrapper left";
    wrapperdiv_.appendChild(subDiv_);
    recieverview_.appendChild(wrapperdiv_);
    countMessage++;
}
function removeuser(idin)
{
    idin = idin.split("(^)");
    var user_ = document.getElementById("person_"+idin[1]);
    var userview_ = document.getElementById("viewer_"+idin[1]);
    console.log("uafaeu :",focusedUser);
    division_alive.removeChild(user_);
    users_list.splice(users_list.indexOf(user_),1);
    if (focusedUser != userview_)
    {
        division_viewerpov.removeChild(userview_);
    }
    else
    {
         division_viewerpov.appendChild(initial_view);
         userview_.textContent='User Lost !';
         focusedUser = null;
    }
}