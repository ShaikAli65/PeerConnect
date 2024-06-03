// +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
const wss = new WebSocket("ws://localhost:50861");
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
    profiles.forEach(profileName => {
        const profileElement = createProfileElement(profileName);
        profileListDiv.appendChild(profileElement);
    });
}
function createProfileElement(profileName) {
    let server_details = "localhost";
    
    try {
        server_details = DATA.content[profileName].CONFIGURATIONS.server_ip;
    }
    catch (TypeError) {console.log('No server ip found for profile:', profileName)}

    const profile = getprofilebox(profileName,server_details);
    profile.id = "!@#" + profileName;
    profile.addEventListener('click', () => {
        profile.classList.add('selected');
        const siblings = Array.from(profileList.children).filter(
        sibling => sibling !== profile
        );
        siblings.forEach(sibling => sibling.classList.remove('selected'));
    });

  return profile;
}
function getprofilebox(profileName, profileDetails) {
    const profileBox = document.createElement('div');
    profileBox.classList.add('card');
  
    const cardDetails = document.createElement('div');
    cardDetails.classList.add('card-details');
  
    const title = document.createElement('p');
    title.classList.add('text-title');
    title.textContent = profileName;
    
    const details = document.createElement('p');
    details.classList.add('text-body');
    details.textContent = profileDetails;
    
    const EditBtn = document.createElement('button');
    EditBtn.classList.add('card-button');
    EditBtn.textContent = 'Edit';
    cardDetails.appendChild(title);
    cardDetails.appendChild(details);
  
    profileBox.appendChild(cardDetails);
    profileBox.appendChild(EditBtn);
    EditBtn.addEventListener('click', ()=>{edit_profile(profileBox, cardDetails,title,details,EditBtn)});
    return profileBox;  
}

function save_changes(profileBox, cardDetails, prevtitle, titleInput,detailsInput,saveBtn) {
    const EditBtn = document.createElement('button');
    EditBtn.classList.add('card-button');
    EditBtn.textContent = 'Edit';
    
    const title = document.createElement('p');
    title.classList.add('text-title');
    title.textContent = titleInput.value;
    
    const details = document.createElement('p');
    details.classList.add('text-body');
    details.textContent = detailsInput.value;
    console.log('prevtitle:',prevtitle);
    DATA.content[prevtitle].CONFIGURATIONS.server_ip = detailsInput.value;
    DATA.content[prevtitle].CONFIGURATIONS.username = titleInput.value;
    profileBox.replaceChild(EditBtn, saveBtn);
    cardDetails.replaceChild(title, titleInput);
    cardDetails.replaceChild(details, detailsInput);
    EditBtn.addEventListener('click', ()=>{edit_profile(profileBox, cardDetails,title,details,EditBtn)});
}

function edit_profile(profileBox, cardDetails,title,details,EditBtn) {

    const saveBtn = document.createElement('button');
    saveBtn.classList.add('card-button');
    saveBtn.textContent = 'Save';
    profileBox.replaceChild(saveBtn, EditBtn);
    const titleInput = document.createElement('input');
    titleInput.classList.add('text-title');
    titleInput.classList.add('editing');
    let prevtitle = title.textContent;
    titleInput.value = prevtitle;
    
    const detailsInput = document.createElement('input');
    detailsInput.classList.add('text-body');
    detailsInput.classList.add('editing');
    detailsInput.value = details.textContent;
    
    cardDetails.replaceChild(titleInput, title);
    saveBtn.addEventListener('click', () => {save_changes(profileBox, cardDetails, prevtitle, titleInput,detailsInput,saveBtn)});
    cardDetails.replaceChild(detailsInput, details);
    
}
addProfileBtn.addEventListener('click', () => {
    const newProfileName = prompt('Enter the name of the new profile:');
    if (newProfileName) {
      const newProfileServerIp = prompt('Enter the server ip of the new profile:');
    DATA.content[newProfileName] = {'CONFIGURATIONS': {'server_ip': newProfileServerIp, 'username': newProfileName, 'server_port': 45000}};
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
    let selected_profile = {'content':dict_selected_profile.CONFIGURATIONS.username,'header':'selected profile','id':''};
    console.log('selected_profile:', selected_profile);
    wss.send(JSON.stringify(selected_profile));
}

function send_fresh_profiles() {
    let modified_profiles = {'content':DATA.content,'header':'new profile list','id':''};
    console.log('modified_profiles:', modified_profiles);
    wss.send(JSON.stringify(modified_profiles));
}

window.onload = initiate_signals;