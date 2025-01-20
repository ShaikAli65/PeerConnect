// +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
const wss = new WebSocket("ws://localhost:28345");
const profileListDiv = document.getElementById('profileList');
const addProfileBtn = document.getElementById('addProfileBtn');
const delProfileBtn = document.getElementById('delProfileBtn');
const proceedBtn = document.getElementById('proceedBtn');
var DATA = {};


function initiate_signals()
{
    wss.addEventListener('message', (event) => {
        DATA = JSON.parse(event.data);
        display_profiles(DATA);
        console.log("profile data :", DATA)
    });
    wss.addEventListener('open', () => {})
    wss.addEventListener('close', () => {})
}
function display_profiles(DATA) {

    let profiles = Object.getOwnPropertyNames(DATA.content);
    console.log(profiles)
    profiles.forEach(profile_id => {
        console.log(profile_id);
    });
    profiles.forEach(profile_id => {
        const profileElement = createProfileElement(profile_id);
        profileListDiv.appendChild(profileElement);
    });
}
function createProfileElement(profile_id) {
    let server_details = "localhost";
    
    try {
        server_details = DATA.content[profile_id].SERVER;
    }
    catch (TypeError) {console.log('No server ip found for profile:', profile_id)}

    const profile = getprofilebox(profile_id,[server_details.ip, server_details.port, server_details.id]);
    profile.id = "!@#" + profile_id;
    profile.addEventListener('click', () => {
        profile.classList.add('selected');
        const siblings = Array.from(profileListDiv.children).filter(
        sibling => sibling !== profile
        );
        siblings.forEach(sibling => sibling.classList.remove('selected'));
    });

  return profile;
}
function getprofilebox(profileId, profileDetails) {
    console.log(profileId,profileDetails)
    const profileBox = document.createElement('div');
    profileBox.classList.add('card');
  
    const cardDetails = document.createElement('div');
    cardDetails.classList.add('card-details');
  
    const title = document.createElement('p');
    title.classList.add('text-title');
    title.textContent = DATA.content[profileId]['USER'].name;
    
    const server_ip = document.createElement('p');
    const server_port = document.createElement('p');
    const server_id = document.createElement('p');
    server_ip.textContent = profileDetails[0];
    server_port.textContent = profileDetails[1];
    server_id.textContent = profileDetails[2];
    server_ip.classList.add('text-body');
    server_port.classList.add('text-body');
    server_id.classList.add('text-body');
    
    const EditBtn = document.createElement('button');
    EditBtn.classList.add('card-button');
    EditBtn.textContent = 'Edit';
    cardDetails.appendChild(title);
    cardDetails.appendChild(server_id);
    cardDetails.appendChild(server_ip);
    cardDetails.appendChild(server_port);
    profileBox.appendChild(cardDetails);
    profileBox.appendChild(EditBtn);
    const details = [server_ip, server_port, server_id]
    EditBtn.addEventListener('click', ()=>{edit_profile(profileBox, cardDetails, profileId, details, EditBtn)});
    return profileBox;  
}

function edit_profile(profileBox, cardDetails, profile_id, details, EditBtn) {
    var title = document.getElementById('!@#'+profile_id);
    title = title.querySelector('.card-details p')
    console.log(title)
    const saveBtn = document.createElement('button');
    saveBtn.classList.add('card-button');
    saveBtn.textContent = 'Save';
    profileBox.replaceChild(saveBtn, EditBtn);
    
    const titleInput = document.createElement('input');
    titleInput.classList.add('text-title');
    titleInput.classList.add('editing');
    let prevtitle = title.textContent;
    titleInput.value = prevtitle;
    
    const detailsInput1 = document.createElement('input');
    const detailsInput2 = document.createElement('input');
    const detailsInput3 = document.createElement('input');
    detailsInput1.value = details[0].textContent;
    detailsInput2.value = details[1].textContent;
    detailsInput3.value = details[2].textContent;
    detailsInput1.classList.add('text-body');
    detailsInput1.classList.add('editing');
    detailsInput2.classList.add('text-body');
    detailsInput2.classList.add('editing');
    detailsInput3.classList.add('text-body');
    detailsInput3.classList.add('editing');

    const detailsInput = [detailsInput1, detailsInput2, detailsInput3]
    cardDetails.replaceChild(titleInput, title);
    saveBtn.addEventListener('click', () => {save_changes(profileBox, cardDetails, profile_id, titleInput,detailsInput,saveBtn)});
    cardDetails.replaceChild(detailsInput1, details[0]);
    cardDetails.replaceChild(detailsInput2, details[1]);
    cardDetails.replaceChild(detailsInput3, details[2]);
}

function save_changes(profileBox, cardDetails, profile_id, titleInput,detailsInput,saveBtn) {
    const EditBtn = document.createElement('button');
    EditBtn.classList.add('card-button');
    EditBtn.textContent = 'Edit';
    
    const title = document.createElement('p');
    title.classList.add('text-title');
    title.textContent = titleInput.value;
    
    const details1 = document.createElement('p');
    const details2 = document.createElement('p');
    const details3 = document.createElement('p');
    details1.textContent = detailsInput[0].value;
    details2.textContent = detailsInput[1].value;
    details3.textContent = detailsInput[2].value;
    details1.classList.add('text-body');
    details2.classList.add('text-body');
    details3.classList.add('text-body');

    // console.log('prevtitle:',profile_id);
    console.log(DATA.content[profile_id])
    DATA.content[profile_id].SERVER.ip = detailsInput[0].value;
    DATA.content[profile_id].SERVER.port = detailsInput[1].value;
    DATA.content[profile_id].SERVER.id = detailsInput[2].value;
    DATA.content[profile_id].USER.name = titleInput.value;

    profileBox.replaceChild(EditBtn, saveBtn);
    cardDetails.replaceChild(title, titleInput);
    cardDetails.replaceChild(details1, detailsInput[0]);
    cardDetails.replaceChild(details2, detailsInput[1]);
    cardDetails.replaceChild(details3, detailsInput[2]);

    const details = [details1, details2, details3]
    EditBtn.addEventListener('click', ()=>{edit_profile(profileBox, cardDetails,profile_id,details,EditBtn)});
}

addProfileBtn.addEventListener('click', () => {
    const newProfileName = prompt('Enter the name of the new profile:');
    if (newProfileName) {
        const newProfileServerId = prompt('Enter server id:');
      const newProfileServerIp = prompt('Enter the server ip:');
      const newProfileServerPort = prompt('Enter server port:')
    DATA.content[newProfileName] = {
        'SERVER': {
            'ip': newProfileServerIp,
            'port': newProfileServerPort,
            'id':newProfileServerId
        },
        'USER': {
            'name': newProfileName,
        }
    };
      const newProfileElement = createProfileElement(newProfileName);
      profileListDiv.appendChild(newProfileElement);
    }
});
delProfileBtn.addEventListener('click', () => {
    const selectedProfile = document.querySelector('.card.selected');
    if (selectedProfile) {
        const profileName = selectedProfile.id.split('!@#')[1];
        delete DATA.content[profileName];
        selectedProfile.remove();
    } else {
        alert('Please select a profile.');
    }
});
function proceed_profiles() {
    const selectedProfile = document.querySelector('.card.selected');
    if (selectedProfile) {
        send_fresh_profiles();
      send_selected_profile(selectedProfile.id.split('!@#')[1]);
      console.log('Proceeding with profile:', selectedProfile);
      let form_group = document.getElementById("form_group");
      let flag = document.createElement("div");
      flag.id = "proceed_flag";
      form_group.appendChild(flag);
    } else {
      alert('Please select a profile.');
    }
}

function send_selected_profile(selected_profile_id) {
    let dict_selected_profile = DATA.content[selected_profile_id];
    let selected_profile = {'content':dict_selected_profile,'header':'selected profile','id':''};
    console.log('selected_profile:', selected_profile);
    wss.send(JSON.stringify(selected_profile));
}

function send_fresh_profiles() {
    let modified_profiles = {'content':DATA.content,'header':'new profile list','id':''};
    console.log('modified_profiles:', modified_profiles);
    wss.send(JSON.stringify(modified_profiles));
}

window.onload = initiate_signals;